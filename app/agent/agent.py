import asyncio
from dataclasses import dataclass, field
from typing import Annotated, Literal

import structlog
from pydantic import StringConstraints
from pydantic_ai import Agent, RunContext
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.models.ollama import OllamaModel
from pydantic_ai.providers.ollama import OllamaProvider
from pydantic_ai.settings import ModelSettings

from app.agent.departments import Department
from app.agent.prompt import SYSTEM_PROMPT
from app.config import settings
from app.ports import EmailSender

log = structlog.get_logger()

RETRY_NUDGE = (
    "You must call the send_to_department tool exactly once. "
    "Do not reply with plain text."
)
FALLBACK_EMAIL_SUBJECT = "Nieprzetworzona wiadomość"
MAX_SUBJECT_CHARS = 120
EmailSubject = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=MAX_SUBJECT_CHARS,
        pattern=r"^[^\r\n]+$",
    ),
]


@dataclass
class RoutedEmail:
    department: Department
    message_id: str
    subject: str


@dataclass
class RoutingDeps:
    sender_email: str
    original_message: str
    email_sender: EmailSender
    routed: RoutedEmail | None = field(default=None, init=False)


@dataclass
class RoutingResult:
    department: Department
    message_id: str
    subject: str
    routed_by: Literal["agent", "fallback"]


def build_agent(
    system_prompt: str, model_name: str | None = None
) -> Agent[RoutingDeps, str]:
    model = OllamaModel(
        model_name or settings.ollama_model,
        provider=OllamaProvider(base_url=settings.ollama_base_url),
        settings=ModelSettings(timeout=settings.ollama_timeout),
    )
    agent: Agent[RoutingDeps, str] = Agent(
        model, deps_type=RoutingDeps, system_prompt=system_prompt
    )

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
        ctx.deps.routed = RoutedEmail(
            department=department, message_id=message_id, subject=subject
        )
        return "sent"

    return agent


agent = build_agent(SYSTEM_PROMPT)


async def route_message(
    message: str,
    sender_email: str,
    email_sender: EmailSender,
    *,
    routing_agent: Agent[RoutingDeps, str] | None = None,
) -> RoutingResult:
    _agent = routing_agent or agent
    for attempt in range(1 + settings.agent_retries):
        deps = RoutingDeps(
            sender_email=sender_email,
            original_message=message,
            email_sender=email_sender,
        )
        prompt = message if attempt == 0 else f"{message}\n\n{RETRY_NUDGE}"

        try:
            async with _agent.iter(prompt, deps=deps) as agent_run:
                async for _node in agent_run:
                    if deps.routed is not None:
                        break
        except UnexpectedModelBehavior as e:
            log.warning("agent_run_rejected", attempt=attempt, error=str(e))

        if deps.routed is not None:
            return RoutingResult(
                department=deps.routed.department,
                message_id=deps.routed.message_id,
                subject=deps.routed.subject,
                routed_by="agent",
            )

    message_id = await asyncio.to_thread(
        email_sender.send,
        to=Department.OTHER.address,
        subject=FALLBACK_EMAIL_SUBJECT,
        body=message,
        reply_to=sender_email,
    )
    return RoutingResult(
        department=Department.OTHER,
        message_id=message_id,
        subject=FALLBACK_EMAIL_SUBJECT,
        routed_by="fallback",
    )
