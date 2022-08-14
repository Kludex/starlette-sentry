import os

import sentry_sdk
from sentry_sdk.integrations.starlette import StarletteIntegration
from starlette.applications import Starlette
from starlette.datastructures import Headers
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route, WebSocketRoute
from starlette.types import ASGIApp, Message
from starlette.websockets import WebSocket

SENTRY_DSN = os.getenv("SENTRY_DSN")


sentry_sdk.init(
    dsn=SENTRY_DSN,
    integrations=[StarletteIntegration("endpoint")],
    # Set traces_sample_rate to 1.0 to capture 100%
    # of transactions for performance monitoring.
    # We recommend adjusting this value in production,
    traces_sample_rate=1.0,
)


async def exception_handler(request: Request, exc: Exception):
    return JSONResponse({"An": "Exception!"})


class CustomHTTPException(Exception):
    ...


class CustomWebSocketException(Exception):
    ...


class CustomMiddlewareException(Exception):
    ...


async def normal(request: Request):
    return JSONResponse({"Hello": "World!"})


async def trigger_error(request: Request):
    raise CustomHTTPException()


def sync_trigger_error(request: Request):
    raise CustomHTTPException()


async def websocket_error(websocket: WebSocket):
    await websocket.accept()
    # NOTE: This raises two exceptions in Sentry.
    # Ref.: https://github.com/encode/starlette/discussions/1787#discussioncomment-3392241
    raise CustomWebSocketException()


class SetUserContext:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        sentry_sdk.set_user({"id": "1"})
        await self.app(scope, receive, send)


class SetExtraContext(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        sentry_sdk.set_context("BaseHTTPMiddleware", {"ha": "ha"})
        return await call_next(request)


class ExceptionOnMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def _send(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = Headers(raw=scope["headers"])
                if headers.get("potato"):
                    raise CustomMiddlewareException()
            await send(message)

        await self.app(scope, receive, _send)


app = Starlette(
    routes=[
        Route("/", normal),
        Route("/sentry-debug", trigger_error),
        Route("/sentry-debug2", sync_trigger_error),
        WebSocketRoute("/sentry-ws", websocket_error),
    ],
    exception_handlers={Exception: exception_handler},
    middleware=[
        Middleware(SetUserContext),
        Middleware(ExceptionOnMiddleware),
        Middleware(SetExtraContext),
    ],
)
