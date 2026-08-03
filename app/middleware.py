from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


class MaxBodySizeMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and self._declared_too_large(scope):
            response = JSONResponse(
                status_code=413,
                content={"detail": f"Request body exceeds {self.max_bytes} bytes"},
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)

    def _declared_too_large(self, scope: Scope) -> bool:
        for name, value in scope["headers"]:
            if name == b"content-length":
                try:
                    return int(value) > self.max_bytes
                except ValueError:
                    return False
        return False
