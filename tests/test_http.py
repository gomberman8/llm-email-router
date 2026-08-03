import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.exceptions import ModelAPIError

from app.agent.agent import RoutingResult
from app.agent.departments import Department
from app.config import settings
from app.dependencies import get_routing_service
from app.exceptions import EmailDeliveryError
from app.main import app


class _SuccessService:
    async def route(self, sender_email: str, message: str) -> RoutingResult:
        return RoutingResult(
            department=Department.HELP_DESK,
            message_id="<test-msg-id>",
            routed_by="agent",
        )


class _CapturingService:
    def __init__(self) -> None:
        self.captured_message: str | None = None

    async def route(self, sender_email: str, message: str) -> RoutingResult:
        self.captured_message = message
        return RoutingResult(
            department=Department.HELP_DESK,
            message_id="<test-msg-id>",
            routed_by="agent",
        )


class _EmailErrorService:
    async def route(self, sender_email: str, message: str) -> RoutingResult:
        raise EmailDeliveryError("smtp down")


class _ModelErrorService:
    async def route(self, sender_email: str, message: str) -> RoutingResult:
        raise ModelAPIError("ollama", "connection refused")


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_invalid_email_returns_422(client: TestClient):
    resp = client.post(
        "/api/v1/route", json={"email": "not-an-email", "message": "hello"}
    )
    assert resp.status_code == 422


def test_message_exceeding_max_length_returns_422(client: TestClient):
    long_msg = "x" * (settings.max_message_chars + 1)
    resp = client.post("/api/v1/route", json={"email": "a@b.com", "message": long_msg})
    assert resp.status_code == 422


def test_empty_message_returns_422(client: TestClient):
    resp = client.post("/api/v1/route", json={"email": "a@b.com", "message": ""})
    assert resp.status_code == 422


def test_whitespace_only_message_returns_422(client: TestClient):
    resp = client.post(
        "/api/v1/route", json={"email": "a@b.com", "message": "   \t\n  "}
    )
    assert resp.status_code == 422


def test_message_with_surrounding_whitespace_is_preserved_unstripped(
    client: TestClient,
):
    service = _CapturingService()
    app.dependency_overrides[get_routing_service] = lambda: service
    original = "  Nie działa drukarka  "
    resp = client.post("/api/v1/route", json={"email": "a@b.com", "message": original})
    assert resp.status_code == 200
    assert service.captured_message == original


def test_message_of_exactly_max_length_is_accepted(client: TestClient):
    app.dependency_overrides[get_routing_service] = lambda: _SuccessService()
    max_msg = "x" * settings.max_message_chars
    resp = client.post("/api/v1/route", json={"email": "a@b.com", "message": max_msg})
    assert resp.status_code == 200


def test_oversized_body_returns_413_without_reading_it(client: TestClient):
    oversized = b"x" * (settings.max_body_bytes + 1)
    resp = client.post(
        "/api/v1/route",
        content=oversized,
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 413
    assert str(settings.max_body_bytes) in resp.json()["detail"]


def test_body_within_limit_still_reaches_validation(client: TestClient):
    resp = client.post("/api/v1/route", json={"email": "nope", "message": "x"})
    assert resp.status_code == 422


class _HangingService:
    async def route(self, sender_email: str, message: str) -> RoutingResult:
        await asyncio.sleep(3600)
        raise AssertionError("unreachable")


def test_routing_that_outlives_request_timeout_returns_504(client: TestClient):
    app.dependency_overrides[get_routing_service] = lambda: _HangingService()
    with patch.object(settings, "request_timeout", 0.05):
        resp = client.post(
            "/api/v1/route", json={"email": "a@b.com", "message": "hello"}
        )
    assert resp.status_code == 504
    assert "retry-after" in resp.headers


def test_semaphore_slot_is_released_after_a_timeout(client: TestClient):
    app.dependency_overrides[get_routing_service] = lambda: _HangingService()
    with patch.object(settings, "request_timeout", 0.05):
        client.post("/api/v1/route", json={"email": "a@b.com", "message": "hello"})

    app.dependency_overrides[get_routing_service] = lambda: _SuccessService()
    resp = client.post("/api/v1/route", json={"email": "a@b.com", "message": "hello"})
    assert resp.status_code == 200


def test_saturated_semaphore_returns_503_with_retry_after(
    client: TestClient, saturated_semaphore
):
    app.dependency_overrides[get_routing_service] = lambda: _SuccessService()
    resp = client.post("/api/v1/route", json={"email": "a@b.com", "message": "hello"})
    assert resp.status_code == 503
    assert "retry-after" in resp.headers


def test_email_delivery_error_returns_503_with_retry_after(client: TestClient):
    app.dependency_overrides[get_routing_service] = lambda: _EmailErrorService()
    resp = client.post("/api/v1/route", json={"email": "a@b.com", "message": "hello"})
    assert resp.status_code == 503
    assert "retry-after" in resp.headers


def test_model_api_error_returns_503_with_retry_after(client: TestClient):
    app.dependency_overrides[get_routing_service] = lambda: _ModelErrorService()
    resp = client.post("/api/v1/route", json={"email": "a@b.com", "message": "hello"})
    assert resp.status_code == 503
    assert "retry-after" in resp.headers


def test_health_returns_200(client: TestClient):
    resp = client.get("/health")
    assert resp.status_code == 200


def _smtp_reachable():
    writer = MagicMock()
    writer.wait_closed = AsyncMock()
    return patch(
        "asyncio.open_connection", new=AsyncMock(return_value=(MagicMock(), writer))
    )


def test_ready_returns_503_when_dependency_unreachable(client: TestClient):
    refused = AsyncMock(side_effect=OSError("refused"))
    with patch("asyncio.open_connection", new=refused):
        resp = client.get("/ready")
    assert resp.status_code == 503
    assert resp.json()["dependencies"]["smtp"] != "ok"


def test_swagger_ui_at_configured_docs_url(client: TestClient):
    resp = client.get("/api/v1/docs")
    assert resp.status_code == 200


def test_openapi_json_contains_route_path(client: TestClient):
    resp = client.get("/api/v1/openapi.json")
    assert resp.status_code == 200
    data = resp.json()
    assert "openapi" in data
    assert "/api/v1/route" in data["paths"]


def test_default_docs_url_not_exposed(client: TestClient):
    resp = client.get("/docs")
    assert resp.status_code == 404


def test_route_success_returns_200_with_full_response(client: TestClient):
    app.dependency_overrides[get_routing_service] = lambda: _SuccessService()
    resp = client.post("/api/v1/route", json={"email": "a@b.com", "message": "hello"})
    assert resp.status_code == 200
    data = resp.json()
    assert "@" in data["department"]
    assert "reasoning" not in data
    assert "routed_by" in data
    assert "message_id" in data
    assert data["processing_time_ms"] >= 0


def test_ready_returns_200_when_all_dependencies_ok(client: TestClient):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"models": [{"name": settings.ollama_model}]}

    mock_inner = MagicMock()
    mock_inner.get = AsyncMock(return_value=mock_resp)

    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_inner)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with _smtp_reachable(), patch("httpx.AsyncClient", return_value=mock_ctx):
        resp = client.get("/ready")

    assert resp.status_code == 200
    deps = resp.json()["dependencies"]
    assert deps["smtp"] == "ok"
    assert deps["ollama"] == "ok"
    assert deps["ollama_model"] == "ok"


def test_ready_returns_503_when_configured_model_not_in_ollama(client: TestClient):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"models": [{"name": "jakis-inny-model"}]}

    mock_inner = MagicMock()
    mock_inner.get = AsyncMock(return_value=mock_resp)

    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_inner)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with _smtp_reachable(), patch("httpx.AsyncClient", return_value=mock_ctx):
        resp = client.get("/ready")

    assert resp.status_code == 503
    deps = resp.json()["dependencies"]
    assert deps["ollama"] == "ok"
    assert deps["ollama_model"] != "ok"
