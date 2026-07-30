from dataclasses import dataclass, field
from typing import Literal

from pydantic_ai import Agent, RunContext
from pydantic_ai.models.ollama import OllamaModel
from pydantic_ai.providers.ollama import OllamaProvider

from app.agent.departments import Department
from app.agent.prompt import SYSTEM_PROMPT
from app.config import settings
from app.ports import EmailSender

RETRY_NUDGE = (
    "You must call the send_to_department tool exactly once. "
    "Do not reply with plain text."
)


@dataclass
class RoutedEmail:
    department: Department
    message_id: str


@dataclass
class RoutingDeps:
    sender_email: str
    email_sender: EmailSender
    routed: RoutedEmail | None = field(default=None, init=False)


@dataclass
class RoutingResult:
    department: Department
    message_id: str
    reasoning: str
    routed_by: Literal["agent", "fallback"]


def build_agent(
    system_prompt: str, model_name: str | None = None
) -> Agent[RoutingDeps, str]:
    model = OllamaModel(
        model_name or settings.ollama_model,
        provider=OllamaProvider(base_url=settings.ollama_base_url),
    )
    agent: Agent[RoutingDeps, str] = Agent(
        model, deps_type=RoutingDeps, system_prompt=system_prompt
    )

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

    return agent


agent = build_agent(SYSTEM_PROMPT)


async def route_message(
    message: str, sender_email: str, email_sender: EmailSender
) -> RoutingResult:
    for attempt in range(1 + settings.agent_retries):
        deps = RoutingDeps(sender_email=sender_email, email_sender=email_sender)
        prompt = message if attempt == 0 else f"{message}\n\n{RETRY_NUDGE}"
        result = await agent.run(prompt, deps=deps)
        if deps.routed is not None:
            return RoutingResult(
                department=deps.routed.department,
                message_id=deps.routed.message_id,
                reasoning=result.output,
                routed_by="agent",
            )

    message_id = email_sender.send(
        to=Department.OTHER.address,
        subject="Nieprzetworzona wiadomość",
        body=message,
        reply_to=sender_email,
    )
    return RoutingResult(
        department=Department.OTHER,
        message_id=message_id,
        reasoning="agent did not call the routing tool after retrying",
        routed_by="fallback",
    )
