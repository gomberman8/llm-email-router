import email
import email.policy
import os

import httpx
import pytest

API_BASE = os.getenv("API_BASE", "http://localhost:8000")
ROUTER_URL = f"{API_BASE}/api/v1/route"
DOCS_URL = f"{API_BASE}/api/v1/docs"
MAILPIT_BASE = os.getenv("MAILPIT_BASE", "http://localhost:8025")
SENDER_EMAIL = "testuser@example.com"
MESSAGE = "Nie działa mi klawiatura od rana, proszę o pomoc."
EXPECTED_DEPARTMENT = "help-desk@example.com"


@pytest.mark.llm
def test_e2e_email_reaches_mailpit_with_correct_headers():
    httpx.delete(f"{MAILPIT_BASE}/api/v1/messages")

    resp = httpx.post(
        ROUTER_URL,
        json={"email": SENDER_EMAIL, "message": MESSAGE},
        timeout=60,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["department"] == EXPECTED_DEPARTMENT

    messages = httpx.get(f"{MAILPIT_BASE}/api/v1/messages").json()
    assert messages["total"] >= 1

    msg_id = messages["messages"][0]["ID"]
    raw_resp = httpx.get(f"{MAILPIT_BASE}/api/v1/message/{msg_id}/raw")
    assert raw_resp.status_code == 200

    parsed = email.message_from_bytes(raw_resp.content, policy=email.policy.default)
    assert parsed["to"] == EXPECTED_DEPARTMENT
    assert parsed["reply-to"] == SENDER_EMAIL
    assert parsed["subject"]
    assert len(parsed["subject"]) <= 120
    decoded_body = parsed.get_content().replace("\r\n", "\n")
    assert decoded_body == f"{MESSAGE}\n"


@pytest.mark.llm
def test_swagger_ui_loads_its_assets_from_the_container():
    html = httpx.get(DOCS_URL).text
    assert "https://" not in html
    assert "/api/v1/swagger-ui/swagger-ui-bundle.js" in html

    for asset in ("swagger-ui-bundle.js", "swagger-ui.css", "favicon-32x32.png"):
        resp = httpx.get(f"{API_BASE}/api/v1/swagger-ui/{asset}")
        assert resp.status_code == 200
        assert resp.content
