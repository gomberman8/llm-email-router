# Routing: department scopes and evaluation

## Five departments

| Department | Scope |
|---|---|
| `kadry` | Payroll and HR administration: leave requests, sick certificates, employment contracts and amendments, pay stubs, tax forms, timesheet records |
| `human-resources` | Soft HR: recruitment, onboarding, training, performance reviews, career paths, team conflicts, workplace culture, non-salary benefits |
| `help-desk` | First-line support, single user: broken printer, crashing app, forgotten password reset, non-working mouse/keyboard/monitor |
| `it` | Infrastructure and security: network/service outages affecting multiple people, servers, VPN, account creation, permissions, security incidents, IT hardware and software procurement |
| `other` | Everything else: accounting invoices, vendor proposals, customer inquiries, office administration, broken non-IT equipment |

## Disambiguation rules for boundary cases

**kadry vs human-resources:** if the matter concerns a document, a formal
entitlement, or money in the paycheck → kadry. If it concerns people,
relationships, or professional development → human-resources.

**help-desk vs it:** if the problem affects one person and their own hardware
or application → help-desk. If it concerns infrastructure, network, permissions,
security, or procurement → it.

Detailed rules (password reset, account creation, IT vs office hardware) are
defined in `app/agent/prompt.py` and `app/agent/departments.py`.

## The dataset

35 Polish messages in `eval/dataset.py`, each labelled with the department it
should reach: 29 used while tuning the prompt, plus 6 added afterwards and never
tuned against, so they act as a held-out check.

Messages are written the way people actually write them, with varying length,
typos, missing Polish diacritics in some and colloquial phrasing, rather than 35
variations of one sentence. The set is loaded with the two overlapping pairs on
purpose, and includes a phishing report that has to reach `it` despite mentioning
a password, which collides with the "password reset goes to help-desk" rule.

Splitting tuned from held-out matters because once a prompt has been adjusted
against a set, that set stops measuring generalisation and starts measuring recall.
Both numbers are reported separately below rather than merged into one figure.

## Evaluation results

Run: `docker compose cp eval api:/app/ && docker compose exec -T api python -m eval.run_eval`  
Repeated runs, not single samples: the 29-case set produced an identical result on
three consecutive runs before the held-out cases were added.

| Model | Tuned (29) | Held-out (6) | s/msg | Fallbacks | Verdict |
|---|---|---|---|---|---|
| `qwen3:4b-instruct` | 29/29 (100%) | 6/6 (100%) | 9.2 | 0 | **selected** |
| `llama3.2:3b` | 18/29 (62%) | 3/6 (50%) | 22.8 | 4 | rejected |
| `qwen3:4b` | did not finish | n/a | >120 s (timeout) | n/a | rejected |

**Caveats:**

- The held-out set (6 cases) is easier than the tuned set. 100% held-out accuracy
  indicates no severe overfitting, but does not guarantee robustness on the hardest
  boundary cases. Several tuned boundary cases also self-disambiguate: a message
  saying "everyone else logs in fine, so it's probably my machine" hands the model
  the single-user signal it needs. The genuinely ambiguous class stays
  under-represented.
- The one failure that survived every run before the prompt was fixed was a broken
  coffee machine routed to `it`. The IT scope said "procurement of new equipment"
  without limiting *equipment* to computing hardware, so the model applied the rule
  correctly and the rule was wrong. Fixed by narrowing the scope text, not by
  changing the label.
- `qwen3:4b` was rejected on latency alone. At the default `OLLAMA_TIMEOUT=120`
  it throws `httpcore.ReadTimeout` before completing most messages. Accuracy was
  not measured.
- `llama3.2:3b` does call the tool correctly but is clearly less accurate and
  slower. Four fallbacks across the full set of 35 messages indicate unstable
  tool-calling reliability with this model and prompt.

## Model ceiling

The point of this project is to keep inference local, entirely inside an Ollama
container with no external API calls, so the models worth testing were bounded
from the start by what the available hardware serves at an acceptable latency.
`qwen3:4b-instruct` is the largest model that stayed within a few seconds per
request on CPU while calling the tool reliably, and `qwen3:4b` was rejected on
latency rather than on quality, its accuracy was never measured.

A larger local model on stronger hardware, or a hosted model behind the same
OpenAI-compatible interface, would very likely do better on exactly what this
dataset under-represents: the genuinely ambiguous messages where the
kadry/human-resources and help-desk/it boundaries overlap. It would also reduce
the load on the retry path, which exists mainly because a 4B model does not
reliably emit a tool call on every turn.

Swapping the model is a configuration change, not a rewrite. The name comes from
`OLLAMA_MODEL`, and the provider is constructed in one place, `build_agent()` in
[`app/agent/agent.py`](../../app/agent/agent.py), so pointing the agent at a
different OpenAI-compatible endpoint touches a single function while the tool,
the enum constraint and the Reply-To handling stay as they are. The accuracy
reported above is best read as a floor set by the hardware on hand, not as a
ceiling of the design.
