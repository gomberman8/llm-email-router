from app.config import settings
from app.main import app as real_app
from app.middleware import MaxBodySizeMiddleware

MAX_BYTES = 20


def _scope(headers=None):
    return {
        "type": "http",
        "method": "POST",
        "path": "/x",
        "headers": headers or [],
        "query_string": b"",
        "http_version": "1.1",
    }


def _make_receive(messages):
    it = iter(messages)

    async def receive():
        return next(it)

    return receive


class _Sent:
    def __init__(self):
        self.messages = []

    async def __call__(self, message):
        self.messages.append(message)

    @property
    def status(self):
        for message in self.messages:
            if message["type"] == "http.response.start":
                return message["status"]
        return None


async def _drain_app(scope, receive, send):
    more_body = True
    while more_body:
        message = await receive()
        if message["type"] == "http.disconnect":
            break
        more_body = message.get("more_body", False)
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b""})


async def test_chunked_request_without_content_length_over_limit_returns_413():
    middleware = MaxBodySizeMiddleware(_drain_app, max_bytes=MAX_BYTES)
    receive = _make_receive(
        [
            {"type": "http.request", "body": b"a" * 10, "more_body": True},
            {"type": "http.request", "body": b"b" * 10, "more_body": True},
            {"type": "http.request", "body": b"c" * 10, "more_body": False},
        ]
    )
    sent = _Sent()

    await middleware(_scope(), receive, sent)

    assert sent.status == 413
    assert str(MAX_BYTES) in sent.messages[-1]["body"].decode()


async def test_understated_content_length_with_larger_actual_body_returns_413():
    middleware = MaxBodySizeMiddleware(_drain_app, max_bytes=MAX_BYTES)
    receive = _make_receive(
        [
            {"type": "http.request", "body": b"a" * 15, "more_body": True},
            {"type": "http.request", "body": b"b" * 15, "more_body": False},
        ]
    )
    sent = _Sent()

    await middleware(_scope(headers=[(b"content-length", b"5")]), receive, sent)

    assert sent.status == 413


async def test_chunked_request_without_content_length_within_limit_reaches_app():
    middleware = MaxBodySizeMiddleware(_drain_app, max_bytes=MAX_BYTES)
    receive = _make_receive(
        [
            {"type": "http.request", "body": b"a" * 5, "more_body": True},
            {"type": "http.request", "body": b"b" * 5, "more_body": True},
            {"type": "http.request", "body": b"c" * 5, "more_body": False},
        ]
    )
    sent = _Sent()

    await middleware(_scope(), receive, sent)

    assert sent.status == 200


async def test_oversized_request_never_invokes_downstream_app():
    received_bodies = []

    async def recording_app(scope, receive, send):
        more_body = True
        while more_body:
            message = await receive()
            if message["type"] == "http.disconnect":
                break
            received_bodies.append(message.get("body", b""))
            more_body = message.get("more_body", False)
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    middleware = MaxBodySizeMiddleware(recording_app, max_bytes=MAX_BYTES)
    receive = _make_receive(
        [
            {"type": "http.request", "body": b"a" * 10, "more_body": True},
            {"type": "http.request", "body": b"b" * 15, "more_body": False},
        ]
    )
    sent = _Sent()

    await middleware(_scope(), receive, sent)

    assert sent.status == 413
    assert received_bodies == []


async def test_early_responding_app_does_not_cause_double_response():
    async def _early_responder_app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        more_body = True
        while more_body:
            message = await receive()
            more_body = message.get("more_body", False)
        await send({"type": "http.response.body", "body": b"ok"})

    middleware = MaxBodySizeMiddleware(_early_responder_app, max_bytes=MAX_BYTES)
    receive = _make_receive(
        [
            {"type": "http.request", "body": b"a" * 10, "more_body": True},
            {"type": "http.request", "body": b"b" * 15, "more_body": False},
        ]
    )
    sent = _Sent()

    await middleware(_scope(), receive, sent)

    assert sent.status == 413
    starts = [m for m in sent.messages if m["type"] == "http.response.start"]
    bodies = [m for m in sent.messages if m["type"] == "http.response.body"]
    assert len(starts) == 1
    assert len(bodies) == 1
    assert b"ok" not in bodies[0]["body"]


async def test_real_app_oversized_streamed_body_returns_413_not_400():
    chunk_size = 4096
    body = b"x" * (settings.max_body_bytes + chunk_size)
    chunks = [body[i : i + chunk_size] for i in range(0, len(body), chunk_size)]
    messages = [
        {"type": "http.request", "body": chunk, "more_body": i < len(chunks) - 1}
        for i, chunk in enumerate(chunks)
    ]
    receive = _make_receive(messages)
    sent = _Sent()
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/route",
        "headers": [
            (b"content-type", b"application/json"),
            (b"content-length", b"5"),
        ],
        "query_string": b"",
        "http_version": "1.1",
        "scheme": "http",
        "server": ("testserver", 80),
        "client": ("testclient", 123),
    }

    await real_app(scope, receive, sent)

    assert sent.status == 413
    body_message = next(m for m in sent.messages if m["type"] == "http.response.body")
    assert str(settings.max_body_bytes) in body_message["body"].decode()


async def test_disconnect_during_buffering_aborts_without_calling_app_or_response():
    called = False

    async def _app(scope, receive, send):
        nonlocal called
        called = True

    middleware = MaxBodySizeMiddleware(_app, max_bytes=MAX_BYTES)
    receive = _make_receive(
        [
            {"type": "http.request", "body": b"a" * 5, "more_body": True},
            {"type": "http.disconnect"},
        ]
    )
    sent = _Sent()

    await middleware(_scope(), receive, sent)

    assert called is False
    assert sent.messages == []
