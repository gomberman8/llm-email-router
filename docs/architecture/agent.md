# Agent: tool calling, security, and retry

## Why a tool call and not a classification

The obvious implementation is to ask the model which department fits, read the
answer, and send the email from application code. This project deliberately does
not do that. The agent is given a tool and **the agent sends the email**; the
application never decides a destination.

The difference is not cosmetic. In the classification design the model's text is
parsed and acted upon, so anything that influences the text influences where mail
goes. Here the model's prose is never read by any code path.

`output_type` is left at its default (`str`) for the same reason: pydantic-ai can
enforce a structured return value, but a structured return is still the model
handing back data for the application to act on. The tool call *is* the action.

## The tool

```python
@agent.tool
def send_to_department(
    ctx: RunContext[RoutingDeps], department: Department, subject: str, body: str
) -> str:
    message_id = ctx.deps.email_sender.send(
        to=department.address,
        subject=subject,
        body=body,
        reply_to=ctx.deps.sender_email,
    )
    ctx.deps.routed = RoutedEmail(department=department, message_id=message_id)
    return f"sent to {department.address}"
```

Three parameters reach the model: `department`, `subject`, `body`. `ctx` is
stripped from the generated JSON schema, so it is invisible to the model. It is a
side channel from the application into the tool body.

`@agent.tool` is used rather than `@agent.tool_plain` precisely because of `ctx`.
Without it the sender address and the `EmailSender` implementation would have to
come from module state, and the address would have to become a tool parameter,
which means something the model controls.

## How the application learns what happened

The tool's return value goes back **to the model**, not to the application; it is
what the model summarises in its final message. The application learns the outcome
through a side effect: the tool writes `RoutedEmail` into `ctx.deps`, and
`RoutingDeps` is an object the caller created and still holds a reference to.

So the success condition is not "the model said it routed the message" but
`deps.routed is not None`, meaning the mail was actually sent. Prose cannot
satisfy it, an invalid tool call cannot satisfy it, and a hallucinated
confirmation cannot satisfy it.

## Why Reply-To comes from deps

`send_to_department` has no `reply_to` parameter. The address is injected from the
HTTP request through `RoutingDeps` and reaches `EmailSender.send()` without ever
passing through the model.

The model cannot change the return address regardless of what it generates. Even
if `subject` or `body` contained an attacker's address, nothing reads them for
routing purposes. This is the architectural defence against prompt injection, and
`test_reply_to_is_sender_email_regardless_of_model_output` enforces it with a
`FunctionModel` that actively tries the injection.

## Enum as a constraint on the destination

`department` is typed as `Department`, so the generated schema is a five-value
enum: `kadry`, `human-resources`, `help-desk`, `it`, `other`. The model picks one
of five; it cannot invent an address. A value outside the enum fails validation
before the tool body runs.

`test_department_parameter_schema_restricted_to_enum_values` asserts the schema
still carries exactly the values of `Department`, so widening the signature to
`to: str` would fail the suite.

## Retry and fallback

Measured against Ollama 0.32.5 with `qwen3:4b-instruct`: sending
`tool_choice="required"` alongside the tools array returns HTTP 200 with a plain
`content` string and no `tool_calls` at all. **The flag is accepted and ignored.**

There is therefore no protocol-level guarantee that a tool call happens, which
makes retry and fallback load-bearing rather than decorative:

1. `agent.run(message)`: if `deps.routed` is set, done, `routed_by="agent"`
2. otherwise `agent.run(message + RETRY_NUDGE)`, a stricter restatement appended
   to the prompt, with a fresh `RoutingDeps`
3. if that also fails, the service sends to `other@` itself and marks
   `routed_by="fallback"`

The loop lives in `route_message()`, outside the agent, because `ModelRetry` can
only be raised from inside a tool that is already executing; it cannot fire when
the model never calls a tool at all, which is exactly this failure mode.

The fallback path is the one place where application code sends mail rather than
the agent. It is flagged in the response so it can never be mistaken for a normal
routing decision, and it exists so the endpoint never returns a 500 because the
model was uncooperative.
