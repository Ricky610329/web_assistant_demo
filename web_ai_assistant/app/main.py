"""One independently deployed assistant; the school's service never runs inference."""

from collections.abc import Callable
from contextlib import asynccontextmanager, aclosing
from pathlib import Path
import asyncio
import ipaddress
import json
import logging
import time
import uuid

import anyio

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from .limiter import AdmissionError, Lease, RequestGuard
from .provider import DemoProvider, IncompleteStreamError, OpenAIProvider, Provider, bounded_close
from .schemas import ChatRequest
from .settings import Settings

logger = logging.getLogger("assistant")
STATIC = Path(__file__).resolve().parent.parent / "static"


def error_response(code: str, message: str, status: int, request_id: str, headers=None):
    return JSONResponse(
        {"error": {"code": code, "message": message}, "request_id": request_id},
        status_code=status, headers=headers,
    )


class RequestBoundary:
    """Bound request bodies before JSON parsing; avoid buffering unbounded input."""

    def __init__(self, app, settings: Settings):
        self.app = app
        self.settings = settings

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        request_id = uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        start = time.monotonic()
        status = 500
        is_chat = scope["path"] == "/api/chat" and scope["method"] == "POST"

        async def safe_send(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = list(message.get("headers", []))
                headers.extend([
                    (b"x-request-id", request_id.encode()),
                    (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"no-referrer"),
                ])
                message = {**message, "headers": headers}
            await send(message)

        try:
            if is_chat:
                headers = dict(scope.get("headers", []))
                raw_length = headers.get(b"content-length")
                if raw_length is not None:
                    try:
                        length = int(raw_length)
                        if length < 0:
                            raise ValueError()
                    except ValueError:
                        return await error_response(
                            "invalid_request", "請求格式不正確。", 400, request_id
                        )(scope, receive, safe_send)
                    if length > self.settings.max_body_bytes:
                        return await error_response(
                            "body_too_large", "訊息資料過大，請縮短內容。", 413, request_id
                        )(scope, receive, safe_send)
                buffered_body = bytearray()
                size = 0
                try:
                    async with asyncio.timeout(self.settings.body_read_timeout_seconds):
                        while True:
                            message = await receive()
                            if message["type"] == "http.disconnect":
                                return
                            if message["type"] != "http.request":
                                continue
                            body = message.get("body", b"")
                            size += len(body)
                            if size > self.settings.max_body_bytes:
                                return await error_response(
                                    "body_too_large", "訊息資料過大，請縮短內容。", 413, request_id
                                )(scope, receive, safe_send)
                            buffered_body.extend(body)
                            if not message.get("more_body", False):
                                break
                except TimeoutError:
                    return await error_response(
                        "request_timeout", "傳送訊息逾時，請重新送出。", 408, request_id
                    )(scope, receive, safe_send)
                consumed = False

                async def bounded_receive():
                    nonlocal consumed
                    if not consumed:
                        consumed = True
                        return {"type": "http.request", "body": bytes(buffered_body), "more_body": False}
                    return await receive()

                await self.app(scope, bounded_receive, safe_send)
            else:
                await self.app(scope, receive, safe_send)
        finally:
            if is_chat:
                logger.info("chat request_id=%s status=%d duration_ms=%d", request_id, status,
                            round((time.monotonic() - start) * 1000))


class LeasedStreamingResponse(StreamingResponse):
    """Release even if the client disconnects before the iterator starts."""

    def __init__(self, content, lease: Lease, time_budget: float, **kwargs):
        super().__init__(content, **kwargs)
        self.lease = lease
        self.time_budget = time_budget

    async def __call__(self, scope, receive, send):
        try:
            # Listen for disconnects even on ASGI >=2.4, while upstream is stalled.
            # One additional second lets a timeout event send; then slow sends stop.
            with anyio.move_on_after(self.time_budget + 1):
                async with anyio.create_task_group() as group:
                    async def stream_response():
                        try:
                            await self.stream_response(send)
                        except OSError:
                            pass  # A closed transport is ordinary client cancellation.
                        finally:
                            group.cancel_scope.cancel()

                    group.start_soon(stream_response)
                    await self.listen_for_disconnect(receive)
                    group.cancel_scope.cancel()
        finally:
            self.lease.release()
            close = getattr(self.body_iterator, "aclose", None)
            if close is not None:
                await bounded_close(close)


def client_ip(request: Request, settings: Settings) -> str:
    peer = request.client.host if request.client else "unknown"
    if peer in settings.trusted_proxy_ips:
        raw = request.headers.get("x-forwarded-for", "")
        try:
            values = [str(ipaddress.ip_address(part.strip())) for part in raw.split(",")]
            return values[0]
        except ValueError:
            pass
    return peer


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def create_app(settings: Settings | None = None, provider: Provider | None = None,
               *, clock: Callable = time.monotonic) -> FastAPI:
    settings = settings or Settings()
    owns_provider = provider is None
    provider = provider or (DemoProvider() if settings.llm_mode == "mock" else OpenAIProvider(settings))
    guard = RequestGuard(settings.max_concurrent_requests, settings.requests_per_minute, clock)

    @asynccontextmanager
    async def lifespan(app):
        yield
        if owns_provider:
            close = getattr(provider, "close", None)
            if close:
                await bounded_close(close)

    app = FastAPI(title="可嵌入網站的 LLM 助手", docs_url=None, redoc_url=None,
                  openapi_url=None, lifespan=lifespan)
    app.state.settings = settings
    app.state.provider = provider
    app.state.guard = guard
    app.add_middleware(RequestBoundary, settings=settings)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc):
        # Pydantic errors may contain submitted content: never return them verbatim.
        return error_response("invalid_request", "訊息格式不正確或超過限制。", 422,
                              request.state.request_id)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc):
        return error_response("http_error", "找不到資源或請求方式不正確。", exc.status_code,
                              request.state.request_id)

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc):
        logger.error("request_id=%s error_type=%s", request.state.request_id, type(exc).__name__)
        return error_response("internal_error", "助手暫時無法回應，請稍後再試。", 500,
                              request.state.request_id)

    @app.get("/healthz")
    async def health():
        return {"status": "ok"}

    @app.get("/api/config")
    async def public_config():
        return {"demo_mode": settings.llm_mode == "mock"}

    @app.get("/embed.js")
    async def embed():
        return FileResponse(STATIC / "embed.js", media_type="application/javascript",
                            headers={"Cache-Control": "no-cache"})

    @app.get("/widget/", response_class=HTMLResponse)
    async def widget():
        # Same-origin standalone access remains possible; hosts are explicitly allowed.
        ancestors = " ".join(["'self'", *settings.allowed_frame_origins])
        return HTMLResponse(
            (STATIC / "widget" / "index.html").read_text(encoding="utf-8"),
            headers={
                "Content-Security-Policy": (
                    "default-src 'self'; script-src 'self'; style-src 'self'; "
                    "connect-src 'self'; img-src 'self' data:; object-src 'none'; "
                    f"base-uri 'none'; form-action 'none'; frame-ancestors {ancestors}"
                ),
                "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
                "Cache-Control": "no-store",
            },
        )

    @app.post("/api/chat")
    async def chat(payload: ChatRequest, request: Request):
        request_id = request.state.request_id
        origin = request.headers.get("origin")
        own_origin = settings.public_base_url or f"{request.url.scheme}://{request.url.netloc}"
        if origin is not None and origin != own_origin:
            return error_response("forbidden_origin", "不允許此來源的聊天請求。", 403, request_id)
        content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            return error_response("invalid_request", "請使用 JSON 傳送訊息。", 415, request_id)
        messages = payload.messages
        if (len(messages) > settings.max_messages or messages[-1].role != "user"
                or any(not m.content.strip() or len(m.content) > settings.max_message_chars for m in messages)
                or sum(len(m.content) for m in messages) > settings.max_total_chars):
            return error_response("invalid_request", "訊息格式不正確或超過限制。", 422, request_id)
        # Only complete user/assistant pairs plus the new user turn are accepted.
        if any(m.role != ("user" if i % 2 == 0 else "assistant") for i, m in enumerate(messages)):
            return error_response("invalid_request", "對話順序不正確。", 422, request_id)
        try:
            lease = guard.acquire(client_ip(request, settings))
        except AdmissionError as exc:
            message = "請求過於頻繁，請稍後再試。" if exc.code == "rate_limited" else "助手目前忙碌，請稍後再試。"
            return error_response(exc.code, message, 429 if exc.code == "rate_limited" else 503,
                                  request_id, {"Retry-After": str(exc.retry_after)})
        upstream_messages = [{"role": "system", "content": settings.system_prompt}]
        upstream_messages.extend(m.model_dump() for m in messages)

        async def generate():
            outcome = "cancelled"
            received_text = False
            try:
                async with asyncio.timeout(settings.request_timeout_seconds):
                    async with aclosing(provider.stream(upstream_messages)) as stream:
                        async for text in stream:
                            if text:
                                received_text = received_text or bool(text.strip())
                                yield sse("delta", {"text": text})
                    if not received_text:
                        raise IncompleteStreamError()
                    outcome = "done"
                    yield sse("done", {})
            except TimeoutError:
                outcome = "timeout"
                yield sse("error", {"code": "timeout", "message": "回答逾時，請稍後再試。"})
            except IncompleteStreamError:
                outcome = "incomplete_stream"
                yield sse("error", {"code": "incomplete_stream", "message": "回答未完整結束，請縮短問題或稍後再試。"})
            except asyncio.CancelledError:
                raise
            except Exception:
                # No upstream body/URL/key in browser errors or logs.
                outcome = "upstream_error"
                yield sse("error", {"code": "upstream_error", "message": "模型服務暫時無法回應，請稍後再試。"})
            finally:
                lease.release()
                logger.info("stream request_id=%s outcome=%s", request_id, outcome)

        return LeasedStreamingResponse(
            generate(), lease, settings.request_timeout_seconds,
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    # check_dir=False allows backend-only tests before frontend assets are generated.
    app.mount("/assets", StaticFiles(directory=STATIC / "assets", check_dir=False), name="assets")
    return app


app = create_app()
