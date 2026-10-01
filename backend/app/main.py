from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import build_router
from app.core.container import AppContainer


def create_app(container=None):
    active = container or AppContainer()

    @asynccontextmanager
    async def lifespan(app):
        await active.start()
        yield
        await active.close()

    app = FastAPI(title="Simple Gemini AI Harness", lifespan=lifespan)
    app.state.container = active
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_credentials=False,
                       allow_methods=["*"], allow_headers=["*"])
    app.include_router(build_router(active))
    return app


app = create_app()
