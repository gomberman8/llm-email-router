import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated
from urllib.parse import urlparse

import httpx
import structlog
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic_ai.exceptions import ModelAPIError

from app.adapters.memory_sender import InMemoryEmailSender
from app.agent.agent import route_message as run_routing_agent
from app.config import settings
from app.dependencies import get_routing_service
from app.exceptions import EmailDeliveryError
from app.guards import acquire_semaphore
from app.middleware import MaxBodySizeMiddleware
from app.models import RouteRequest, RouteResponse
from app.services import RoutingService

log = structlog.get_logger()


def _configure_logging() -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.log_level, logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


async def _bind_request_id() -> None:
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id=str(uuid.uuid4())[:8])


@asynccontextmanager
async def lifespan(app: FastAPI):
    _configure_logging()
    if settings.warmup_on_startup:
        try:
            await run_routing_agent(
                message="ping",
                sender_email="warmup@example.com",
                email_sender=InMemoryEmailSender(),
            )
            log.info("warmup_ok")
        except Exception as e:
            log.warning("warmup_failed", error_type=type(e).__name__, error=str(e))
    yield


DOCS_URL = "/api/v1/docs"
OPENAPI_URL = "/api/v1/openapi.json"
SWAGGER_ASSET_ROUTE = "/api/v1/swagger-ui"
SWAGGER_CDN = "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5"
FASTAPI_FAVICON = "https://fastapi.tiangolo.com/img/favicon.png"


def swagger_asset_base(directory: str) -> str:
    if directory and Path(directory).is_dir():
        return SWAGGER_ASSET_ROUTE
    return SWAGGER_CDN


app = FastAPI(
    title="LLM Email Router",
    description="Routes free-form messages to the right department via an LLM agent.",
    version="1.0.0",
    docs_url=None,
    openapi_url=OPENAPI_URL,
    redoc_url=None,
    lifespan=lifespan,
)

app.add_middleware(MaxBodySizeMiddleware, max_bytes=settings.max_body_bytes)

_swagger_base = swagger_asset_base(settings.swagger_ui_dir)
if _swagger_base == SWAGGER_ASSET_ROUTE:
    app.mount(
        SWAGGER_ASSET_ROUTE,
        StaticFiles(directory=settings.swagger_ui_dir),
        name="swagger-ui",
    )


@app.get(DOCS_URL, include_in_schema=False)
def swagger_ui() -> HTMLResponse:
    favicon = (
        f"{_swagger_base}/favicon-32x32.png"
        if _swagger_base == SWAGGER_ASSET_ROUTE
        else FASTAPI_FAVICON
    )
    return get_swagger_ui_html(
        openapi_url=OPENAPI_URL,
        title=app.title,
        swagger_js_url=f"{_swagger_base}/swagger-ui-bundle.js",
        swagger_css_url=f"{_swagger_base}/swagger-ui.css",
        swagger_favicon_url=favicon,
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
    return JSONResponse(status_code=200, content={"fastapi": True})


def qualified_model_name(model: str) -> str:
    return model if ":" in model else f"{model}:latest"


@app.get("/ready", tags=["ops"])
async def readiness_check() -> JSONResponse:
    deps = {"smtp": "ok", "ollama": "ok", "ollama_model": "ok"}
    status_code = 200

    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(settings.smtp_host, settings.smtp_port),
            timeout=settings.ready_timeout,
        )
        writer.close()
        await writer.wait_closed()
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
            if qualified_model_name(settings.ollama_model) not in models:
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


def _elapsed_ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)


@app.post(
    "/api/v1/route",
    dependencies=[Depends(acquire_semaphore), Depends(_bind_request_id)],
)
async def route_message(
    payload: RouteRequest,
    routing_service: Annotated[RoutingService, Depends(get_routing_service)],
) -> RouteResponse:
    start_time = time.monotonic()
    log.info(
        "route_request_received",
        sender_domain=payload.email.split("@")[-1],
        message_chars=len(payload.message),
    )

    try:
        result = await asyncio.wait_for(
            routing_service.route(sender_email=payload.email, message=payload.message),
            timeout=settings.request_timeout,
        )
    except TimeoutError:
        log.warning("route_request_timeout", timeout_seconds=settings.request_timeout)
        raise HTTPException(
            status_code=504,
            detail="Routing timed out",
            headers={"Retry-After": str(settings.retry_after_seconds)},
        ) from None

    processing_time_ms = _elapsed_ms(start_time)

    log.info(
        "route_request_completed",
        department=str(result.department),
        subject=result.subject,
        routed_by=result.routed_by,
        processing_time_ms=processing_time_ms,
    )

    return RouteResponse(
        department=result.department.address,
        subject=result.subject,
        message_id=result.message_id,
        routed_by=result.routed_by,
        processing_time_ms=processing_time_ms,
    )
