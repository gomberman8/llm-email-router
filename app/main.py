import logging
import socket
import time
from contextlib import asynccontextmanager
from typing import Annotated
from urllib.parse import urlparse

import httpx
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic_ai.exceptions import ModelAPIError

from app.adapters.memory_sender import InMemoryEmailSender
from app.agent.agent import RoutingDeps, agent
from app.config import settings
from app.dependencies import get_routing_service
from app.exceptions import EmailDeliveryError
from app.guards import acquire_semaphore
from app.models import RouteRequest, RouteResponse
from app.services import RoutingService

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=settings.log_level)
    if settings.warmup_on_startup:
        try:
            deps = RoutingDeps(
                sender_email="warmup@example.com", email_sender=InMemoryEmailSender()
            )
            await agent.run("ping", deps=deps)
            logger.info("Warmup completed successfully.")
        except Exception as e:  # noqa: BLE001
            logger.warning("Warmup failed: %s", e)
    yield


app = FastAPI(
    title="LLM Email Router",
    description="Routes free-form messages to the right department via an LLM agent.",
    version="1.0.0",
    docs_url="/api/v1/docs",
    openapi_url="/api/v1/openapi.json",
    redoc_url=None,
    lifespan=lifespan,
)


@app.exception_handler(ModelAPIError)
async def model_api_error_handler(request: Request, exc: ModelAPIError):
    return JSONResponse(
        status_code=503,
        content={"detail": "Model API is currently unavailable"},
        headers={"Retry-After": str(settings.retry_after_seconds)},
    )


@app.exception_handler(EmailDeliveryError)
async def email_delivery_error_handler(request: Request, exc: EmailDeliveryError):
    return JSONResponse(
        status_code=503,
        content={"detail": "Email delivery service is currently unavailable"},
        headers={"Retry-After": str(settings.retry_after_seconds)},
    )


@app.get("/health", tags=["ops"])
def health_check() -> JSONResponse:
    """Liveness. Says nothing about dependencies - see /ready for those."""
    return JSONResponse(status_code=200, content={"fastapi": True})


@app.get("/ready", tags=["ops"])
async def readiness_check() -> JSONResponse:
    deps = {"smtp": "ok", "ollama": "ok", "ollama_model": "ok"}
    status_code = 200

    try:
        with socket.create_connection(
            (settings.smtp_host, settings.smtp_port), timeout=settings.smtp_timeout
        ):
            pass
    except OSError as e:
        deps["smtp"] = str(e)
        status_code = 503

    try:
        parsed_url = urlparse(settings.ollama_base_url)
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
        async with httpx.AsyncClient(timeout=settings.ready_timeout) as client:
            resp = await client.get(f"{base_url}/api/tags")
            resp.raise_for_status()
            models_data = resp.json().get("models", [])
            models = [m["name"] for m in models_data]
            if settings.ollama_model not in models:
                deps["ollama_model"] = (
                    f"Model {settings.ollama_model} not found. Available: {models}"
                )
                status_code = 503
    except (httpx.HTTPError, ValueError, KeyError) as e:
        deps["ollama"] = str(e)
        deps["ollama_model"] = "skipped due to ollama connection error"
        status_code = 503

    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ok" if status_code == 200 else "error",
            "dependencies": deps,
        },
    )


@app.post("/api/v1/route", dependencies=[Depends(acquire_semaphore)])
async def route_message(
    request: RouteRequest,
    routing_service: Annotated[RoutingService, Depends(get_routing_service)],
) -> RouteResponse:
    start_time = time.time()
    result = await routing_service.route(
        sender_email=request.email, message=request.message
    )
    processing_time_ms = int((time.time() - start_time) * 1000)

    return RouteResponse(
        department=result.department.address,
        reasoning=result.reasoning,
        message_id=result.message_id,
        routed_by=result.routed_by,
        processing_time_ms=processing_time_ms,
    )
