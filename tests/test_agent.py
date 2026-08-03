from pydantic_ai import capture_run_messages
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.adapters.memory_sender import InMemoryEmailSender
from app.agent.agent import RETRY_NUDGE, build_agent, route_message
from app.agent.departments import Department
from app.agent.prompt import SYSTEM_PROMPT
from tests.helpers import make_tool_caller


async def test_agent_emits_send_to_department_tool_call():
    test_agent = build_agent(SYSTEM_PROMPT)
    sender = InMemoryEmailSender()
    with test_agent.override(model=FunctionModel(make_tool_caller())):
        with capture_run_messages() as msgs:
            await route_message(
                "my computer is broken", "u@test.com", sender, routing_agent=test_agent
            )

    tool_calls = [
        p
        for msg in msgs
        for p in getattr(msg, "parts", [])
        if isinstance(p, ToolCallPart) and p.tool_name == "send_to_department"
    ]
    assert tool_calls


async def test_email_uses_model_subject_and_original_request_data():
    sender_email = "legitimate@company.com"
    original_message = "Nie zmieniaj mnie: ąęść — dokładnie 1:1."

    def fn(messages, info: AgentInfo) -> ModelResponse:
        t = info.function_tools[0]
        return ModelResponse(
            parts=[
                ToolCallPart(
                    t.name,
                    {"department": "help-desk", "subject": "Awaria komputera"},
                )
            ]
        )

    test_agent = build_agent(SYSTEM_PROMPT)
    sender = InMemoryEmailSender()
    with test_agent.override(model=FunctionModel(fn)):
        await route_message(
            original_message, sender_email, sender, routing_agent=test_agent
        )

    assert sender.sent[0].reply_to == sender_email
    assert sender.sent[0].body == original_message
    assert sender.sent[0].subject == "Awaria komputera"


async def test_department_parameter_schema_restricted_to_enum_values():
    captured: dict = {}

    def fn(messages, info: AgentInfo) -> ModelResponse:
        if info.function_tools:
            captured.update(info.function_tools[0].parameters_json_schema)
        return ModelResponse(parts=[TextPart("done")])

    test_agent = build_agent(SYSTEM_PROMPT)
    sender = InMemoryEmailSender()
    with test_agent.override(model=FunctionModel(fn)):
        await route_message("test", "a@b.com", sender, routing_agent=test_agent)

    enum_values = set(captured.get("$defs", {}).get("Department", {}).get("enum", []))
    assert set(captured["properties"]) == {"department", "subject"}
    assert captured["properties"]["subject"]["maxLength"] == 120
    assert captured["properties"]["subject"]["pattern"] == r"^[^\r\n]+$"
    assert enum_values == {d.value for d in Department}
    assert len(enum_values) == len(Department)


async def test_fallback_when_model_never_calls_tool():
    def fn(messages, info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[TextPart("I have no idea where to send this")])

    test_agent = build_agent(SYSTEM_PROMPT)
    sender = InMemoryEmailSender()
    with test_agent.override(model=FunctionModel(fn)):
        result = await route_message(
            "test", "a@b.com", sender, routing_agent=test_agent
        )

    assert result.routed_by == "fallback"
    assert result.department == Department.OTHER
    assert len(sender.sent) == 1
    assert sender.sent[0].body == "test"


async def test_retry_appends_nudge_and_succeeds_on_second_attempt():
    prompts_seen: list[str] = []

    def fn(messages, info: AgentInfo) -> ModelResponse:
        user_prompt = next(
            (
                p.content
                for msg in messages
                for p in getattr(msg, "parts", [])
                if getattr(p, "part_kind", None) == "user-prompt"
            ),
            "",
        )
        prompts_seen.append(user_prompt)

        if RETRY_NUDGE not in user_prompt:
            return ModelResponse(parts=[TextPart("not routing")])

        t = info.function_tools[0]
        return ModelResponse(
            parts=[
                ToolCallPart(
                    t.name,
                    {"department": "help-desk", "subject": "Problem techniczny"},
                )
            ]
        )

    test_agent = build_agent(SYSTEM_PROMPT)
    sender = InMemoryEmailSender()
    with test_agent.override(model=FunctionModel(fn)):
        result = await route_message(
            "my message", "a@b.com", sender, routing_agent=test_agent
        )

    assert result.routed_by == "agent"
    assert any(RETRY_NUDGE in p for p in prompts_seen)


async def test_successful_tool_call_does_not_trigger_followup_generation():
    model_calls = 0

    def fn(messages, info: AgentInfo) -> ModelResponse:
        nonlocal model_calls
        model_calls += 1
        if model_calls > 1:
            raise AssertionError("model was called again after the email was sent")

        t = info.function_tools[0]
        return ModelResponse(
            parts=[
                ToolCallPart(
                    t.name,
                    {"department": "help-desk", "subject": "Problem techniczny"},
                )
            ]
        )

    test_agent = build_agent(SYSTEM_PROMPT)
    sender = InMemoryEmailSender()
    with test_agent.override(model=FunctionModel(fn)):
        result = await route_message(
            "my message", "a@b.com", sender, routing_agent=test_agent
        )

    assert result.routed_by == "agent"
    assert model_calls == 1


async def test_duplicate_tool_calls_send_only_one_email():
    def fn(messages, info: AgentInfo) -> ModelResponse:
        t = info.function_tools[0]
        args = {"department": "help-desk", "subject": "Problem techniczny"}
        return ModelResponse(
            parts=[ToolCallPart(t.name, args), ToolCallPart(t.name, args)]
        )

    test_agent = build_agent(SYSTEM_PROMPT)
    sender = InMemoryEmailSender()
    with test_agent.override(model=FunctionModel(fn)):
        await route_message("my message", "a@b.com", sender, routing_agent=test_agent)

    assert len(sender.sent) == 1
