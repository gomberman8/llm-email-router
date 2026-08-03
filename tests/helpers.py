from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo


def has_tool_return(messages) -> bool:
    return any(
        getattr(p, "part_kind", None) == "tool-return"
        for msg in messages
        for p in getattr(msg, "parts", [])
    )


def make_tool_caller(
    department: str = "help-desk",
    subject: str = "Awaria sprzętu",
):
    def fn(messages, info: AgentInfo) -> ModelResponse:
        if has_tool_return(messages):
            return ModelResponse(parts=[TextPart("routed")])
        t = info.function_tools[0]
        return ModelResponse(
            parts=[
                ToolCallPart(
                    t.name,
                    {"department": department, "subject": subject},
                )
            ]
        )

    return fn
