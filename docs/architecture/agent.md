# Agent: tool calling, security, and retry

## Why a tool call and not a classification

The obvious implementation is to ask the model which department fits, read the
answer, and send the email from application code. This project deliberately does
not do that. The agent is given a tool and **the agent sends the email**; the
application never decides a destination.

The difference is not cosmetic. In the classification design the model's text is
parsed and acted upon, so anything that influences the text influences where mail
goes. Here the model's prose is never read by any code path. A successful run ends
immediately after the tool executes, so the model does not generate a confirmation
afterwards either.

`output_type` is left at its default (`str`) for the same reason: pydantic-ai can
enforce a structured return value, but a structured return is still the model
handing back data for the application to act on. The tool call *is* the action.

## The tool

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

Two parameters reach the model: `department` and `subject`. The subject is a
non-empty string limited to 120 characters with CR/LF forbidden, preventing
header injection. `ctx` is stripped from the generated JSON schema, so the sender
address, original message and transport are invisible to the model. They form a
trusted side channel from the HTTP request into the tool body.

Tool calls are executed sequentially and the `routed` guard makes a repeated call
within the same model response a no-op, preventing duplicate delivery.

`@agent.tool` is used rather than `@agent.tool_plain` precisely because of `ctx`.
Without it the original input and the `EmailSender` implementation would have to
come from module state or become tool parameters, which would put trusted data
under model control.

## How the application learns what happened

The application learns the outcome through a side effect: the tool writes
`RoutedEmail` into `ctx.deps`, and `RoutingDeps` is an object the caller created
and still holds a reference to.

`route_message()` drives the pydantic-ai graph with `agent.iter()` and stops as
soon as `deps.routed` is set. A normal `agent.run()` would send the tool result
back to the model and ask for a final response, even though the mail has already
been sent. Stopping the graph removes that redundant second generation.

So the success condition is not "the model said it routed the message" but
`deps.routed is not None`, meaning the mail was actually sent. Prose cannot
satisfy it, an invalid tool call cannot satisfy it, and a hallucinated
confirmation cannot satisfy it.

## Why the original body and Reply-To come from deps

`send_to_department` has no `body` or `reply_to` parameters. The original body
and sender address are injected from the HTTP request through `RoutingDeps` and
reach `EmailSender.send()` without ever passing through model output. The model
creates only the short subject because summarising the issue in a header is useful
and does not replace user data.

The model therefore cannot paraphrase, truncate or replace the user's message,
nor change the return address. This is the architectural defence against both
data loss and prompt injection. `test_email_uses_model_subject_and_original_request_data`
asserts both trusted values at the sender boundary, while the tool schema test
asserts that the model controls only `department` and the constrained `subject`.

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

1. drive `agent.iter(message)` until the tool succeeds or the run ends
2. if no tool ran, repeat with `message + RETRY_NUDGE` and a fresh `RoutingDeps`
3. if that also fails, the service sends to `other@` itself and marks
   `routed_by="fallback"`

The loop lives in `route_message()`, outside the agent, because `ModelRetry` can
only be raised from inside a tool that is already executing; it cannot fire when
the model never calls a tool at all, which is exactly this failure mode.

The fallback path is the one place where application code sends mail rather than
the agent. It is flagged in the response so it can never be mistaken for a normal
routing decision, and it exists so the endpoint never returns a 500 because the
model was uncooperative.
