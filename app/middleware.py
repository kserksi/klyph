from __future__ import annotations

from fastapi import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


def content_security_policy(script_hashes: tuple[str, ...] = ()) -> str:
    hashes = " ".join(f"'{value}'" for value in script_hashes)
    script_source = "script-src 'self'" + (f" {hashes}" if hashes else "")
    return (
        "default-src 'self'; img-src 'self'; style-src 'self'; "
        f"{script_source}; connect-src 'self'; "
        "font-src 'self' data:; frame-ancestors 'none'; "
        "base-uri 'none'; form-action 'none'"
    )


SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Content-Security-Policy": content_security_policy(),
}


class RequestBodyLimitMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        content_length = headers.get(b"content-length")
        if content_length is not None:
            try:
                declared_length = int(content_length)
            except ValueError:
                await self._reject(scope, receive, send, 400, "invalid content length")
                return
            if declared_length < 0:
                await self._reject(scope, receive, send, 400, "invalid content length")
                return
            if declared_length > self.max_bytes:
                await self._reject(scope, receive, send, 413, "request body too large")
                return

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise HTTPException(status_code=413, detail="request body too large")
            return message

        await self.app(scope, limited_receive, send)

    @staticmethod
    async def _reject(
        scope: Scope, receive: Receive, send: Send, status_code: int, detail: str
    ) -> None:
        response = JSONResponse(
            {"detail": detail},
            status_code=status_code,
            headers=SECURITY_HEADERS,
        )
        await response(scope, receive, send)
