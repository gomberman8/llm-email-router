# Architecture

![System architecture](architecture.drawio.svg)

## Request path

`POST /api/v1/route` validates the payload, takes one of two concurrency slots, and
hands the message to `RoutingService`. The service runs a pydantic-ai agent against
Ollama over its OpenAI-compatible endpoint. The agent calls `send_to_department`,
which sends the mail through an `EmailSender`. The response carries the destination
address, the SMTP message id and which path produced it.

## The agent sends the mail

`send_to_department` takes exactly two arguments:

```python
@agent.tool(sequential=True)
def send_to_department(
    ctx: RunContext[RoutingDeps], department: Department, subject: EmailSubject
) -> str:
    if ctx.deps.routed is not None:
        return "already sent"

    message_id = ctx.deps.email_sender.send(
        to=department.address,
        subject=subject,
        body=ctx.deps.original_message,
        reply_to=ctx.deps.sender_email,
    )
    ctx.deps.routed = RoutedEmail(department=department, message_id=message_id)
    return "sent"
```

`department` is the `Department` enum, so the JSON schema offers five values and
nothing else. `subject` is capped at 120 characters with CR and LF rejected, which
keeps it from becoming a header injection vector.

Body and `Reply-To` are not parameters. They travel from the HTTP request through
`RoutingDeps` and reach the transport without passing through anything the model
generated. A message instructing the model to change the reply address or rewrite
the body has nothing to act on — those fields are not exposed. Verified by
`test_email_uses_model_subject_and_original_request_data` and by the tool schema
test.

## Who the mail looks like it came from

The router is not an authorization step. It decides where a request goes, not
whether it should be granted. "Przelej mi 10k zł" reaching `kadry@` is the correct
outcome — payroll owns that question — and a human still has to answer it.

What the routing does change is how the message looks in the destination inbox. The
subject is written by the model out of the sender's own words, so a hostile sender
gets to choose what a department reads on its message list. With a bare
`From: router@example.com` that text arrives looking like an instruction from an
internal system.

The `From` header therefore names the sender and keeps the router's address:

```
From: "jan.nowak@example.com via LLM Router" <router@example.com>
Reply-To: jan.nowak@example.com
```

Mailing lists solve the same problem the same way. The sender is visible without
opening the message, replies still reach the original author, and nothing on the
list looks like it came from the system itself. `formataddr` quotes and escapes the
display name, so the address cannot break out of the header.

The application never reads the model's prose. Success means `deps.routed` was set,
which only happens after `EmailSender.send()` returned. `route_message()` drives the
graph with `agent.iter()` and stops there, so no confirmation turn is generated
after the mail is already gone.

## When the model misbehaves

Ollama accepts `tool_choice="required"` and ignores it: with `qwen3:4b-instruct` the
request returns 200 with a plain content string and no `tool_calls`. There is no
protocol guarantee that a tool call happens, so the surrounding loop matters.

1. Run the agent. Stop as soon as the tool succeeds.
2. No tool call, or a tool call the model could not get past validation
   (`UnexpectedModelBehavior`): retry once with `RETRY_NUDGE` appended.
3. Still nothing: the application sends to `other@` itself and returns
   `routed_by: "fallback"`.

Both failure modes land in the same place, so an uncooperative model produces a
routed email rather than a 500. `ModelRetry` cannot cover this, since it only fires
from inside a tool that is already executing.

## Departments

| Department | Scope |
|---|---|
| `kadry` | Payroll and HR admin: leave requests, sick notes, contracts, pay stubs, tax forms, timesheets |
| `human-resources` | Soft HR: recruitment, onboarding, training, reviews, team conflicts, non-salary benefits |
| `help-desk` | One user, one device: broken printer, crashing app, forgotten password, dead mouse or monitor |
| `it` | Infrastructure and security: outages affecting several people, servers, VPN, accounts and permissions, incidents, IT procurement |
| `other` | Everything else: invoices, vendor offers, customer mail, office admin, non-IT equipment |

Two boundaries need a rule. Documents, entitlements and money go to `kadry`; people
and development go to `human-resources`. A single person's own hardware goes to
`help-desk`; anything touching infrastructure, permissions or purchasing goes to
`it`. Both rules live in `app/agent/prompt.py`.

## Model choice

35 labelled Polish messages in `eval/dataset.py`: 29 used while tuning the prompt,
6 added afterwards and never tuned against.

| Model | Tuned (29) | Held-out (6) | s/msg | Fallbacks |
|---|---|---|---|---|
| `qwen3:4b-instruct` | 29/29 | 6/6 | 9.2 | 0 |
| `llama3.2:3b` | 18/29 | 3/6 | 22.8 | 4 |
| `qwen3:4b` | did not finish | n/a | >120 s | n/a |

`qwen3:4b` timed out before finishing most messages, so its accuracy is unknown. It
was rejected on latency, not quality.

One failure survived every run early on: a broken coffee machine went to `it`. The
IT scope said "procurement of new equipment" without limiting equipment to computing
hardware, so the model applied the rule correctly and the rule was wrong. Narrowing
the scope text fixed it.

## Containers

```
ollama ──> ollama-init ──> api ──> stack-ready
mailpit ─────────────────> api
```

`ollama-init` pulls the weights and exits. It checks `ollama list` first, so a
restart with the model already in the volume needs no network — without that check
`ollama pull` contacts the registry every time and an offline start fails outright.

`stack-ready` exists so plain `docker compose up -d` is enough. Compose waits for
`depends_on` conditions of the services it starts, but nothing depended on `api`,
so `up -d` used to return while the API was still loading the model. `stack-ready`
depends on `api` being healthy and then exits, which makes `up -d` block until the
endpoint actually answers. It also turns a failed startup into a non-zero exit
instead of a silent one.

`OLLAMA_KEEP_ALIVE=-1` pins the model in memory. Ollama's default evicts it after
five idle minutes, and the next request then pays a full reload — measured at 36 s
against 4 s warm.

Ollama's port is not published. It is reachable only inside the compose network,
because exposing it would expose an unauthenticated model API. That is why `eval/`
runs through `docker compose exec`.

Bind mounts carry `:z`. Without it, SELinux in enforcing mode denies the container
access to the mounted file and `ollama-init` exits with code 2. Docker ignores the
label where SELinux is not active.

Swagger UI's JavaScript and CSS are baked into the image and served from
`/api/v1/swagger-ui`. FastAPI's default pulls them from a CDN, which would make the
docs page blank on a machine without internet. Outside Docker, `SWAGGER_UI_DIR` is
unset and the CDN default applies.

### GPU

```bash
docker compose -f docker-compose.yml -f docker-compose.rocm.yml up -d
docker compose -f docker-compose.yml -f docker-compose.cuda.yml up -d
```

ROCm is verified on a Radeon RX 9070 XT (RDNA4, `gfx1201`) under Fedora 43: 37/37
layers offloaded, 0.73-0.77 s per request against 3.74-3.98 s on the same machine's
CPU. `HSA_OVERRIDE_GFX_VERSION` was not needed. No `group_add` either — the device
nodes are `crw-rw-rw-` and the container runs as root.

**The CUDA override has never been run on GPU hardware.** Only its compose syntax is
validated.

## Tests

`pytest` runs 44 unit tests in under a second with no Ollama and no Mailpit.
`pytest -m llm` adds two tests that need the running stack.

`test_middleware.py` is separate from `test_http.py` because `TestClient` always
sends a correct, buffered request. It cannot produce chunked transfer encoding or a
`Content-Length` that understates the body, so `MaxBodySizeMiddleware` is driven at
the ASGI level instead — proving that an oversized body never reaches the
application, not even truncated.

The e2e test reads Mailpit's raw RFC 2822 source rather than a convenience JSON
field, and checks `To`, `Reply-To` and the decoded body on the wire.

## Known limits

- The held-out set is six messages and easier than the tuned set. Genuinely
  ambiguous messages are under-represented, so 100% is a floor for this dataset
  rather than a general accuracy claim.
- `subject` is written by the model from the user's text, so a hostile sender
  influences what a department sees in its inbox. Header injection is blocked and
  `From` names the sender, but the wording itself is not filtered.
- No queue, no auth, no persistence. Two concurrent runs, then 503 with
  `Retry-After`.
- A larger local model or a hosted one behind the same OpenAI-compatible interface
  would likely do better on the boundary cases. `OLLAMA_MODEL` and `build_agent()`
  are the only places involved.
