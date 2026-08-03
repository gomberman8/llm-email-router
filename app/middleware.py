from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class MaxBodySizeMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if self._declared_too_large(scope):
            await self._send_413(scope, receive, send)
            return

        chunks: list[bytes] = []
        total = 0

        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body = message.get("body", b"")
            total += len(body)
            if total > self.max_bytes:
                await self._send_413(scope, receive, send)
                return
            if body:
                chunks.append(body)
            if not message.get("more_body", False):
                break

        replayed: list[Message] = [
            {"type": "http.request", "body": b"".join(chunks), "more_body": False}
        ]
        replay_iter = iter(replayed)

        async def replaying_receive() -> Message:
            try:
                return next(replay_iter)
            except StopIteration:
                return await receive()

        await self.app(scope, replaying_receive, send)

    def _declared_too_large(self, scope: Scope) -> bool:
        for name, value in scope["headers"]:
            if name == b"content-length":
                try:
                    return int(value) > self.max_bytes
                except ValueError:
                    return False
        return False

    async def _send_413(self, scope: Scope, receive: Receive, send: Send) -> None:
        response = JSONResponse(
            status_code=413,
            content={"detail": f"Request body exceeds {self.max_bytes} bytes"},
        )
        await response(scope, receive, send)
