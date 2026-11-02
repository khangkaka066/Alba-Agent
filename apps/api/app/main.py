"""FastAPI control plane with explicit resource ownership and teardown."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

os.environ["OTEL_SDK_DISABLED"] = "true"
os.environ["CREWAI_DISABLE_TELEMETRY"] = "true"
os.environ["LITELLM_TELEMETRY_DISABLED"] = "true"
os.environ["LITELLM_OFFLINE_MODE"] = "true"

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.auth.local import ensure_local_workspace, local_mode_enabled
from app.auth.router import router as auth_router
from app.billing.router import router as billing_router
from app.routers import analytics, approvals, architect, artifacts, conversations, evolution, knowledge, learning_transfer, providers, sandboxes, self_healing, skills_tools, subscriptions, teammates, templates, time_travel, workflows
from app.services import AppServices, create_default_services


LOCAL_ORIGIN_PATTERN = r"^http://(localhost|127\.0\.0\.1)(:\d{1,5})?$"


def create_app(services: AppServices | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        owns_services = services is None
        if services is None:
            from app.workers.jobs import CeleryDispatcher

            application.state.services = await create_default_services(CeleryDispatcher())
        else:
            application.state.services = services
        await application.state.services.dispatcher.startup()
        if local_mode_enabled() and os.environ.get("NEXUS_SETUP_DATABASE_URL"):
            try:
                await ensure_local_workspace(os.environ["NEXUS_SETUP_DATABASE_URL"])
            except Exception:  # noqa: BLE001 - the app must still start; the first session request retries the seed
                logging.getLogger("nexus.local").exception("Could not seed the local workspace at startup")
        try:
            yield
        finally:
            await application.state.services.dispatcher.shutdown()
            if owns_services:
                await application.state.services.shutdown()

    application = FastAPI(
        title=os.environ.get("NEXUS_BRAND_NAME", "NexusAgent Studio"),
        version="1.0.0", lifespan=lifespan,
    )
    cors_origins = [
        origin.strip()
        for origin in os.environ.get(
            "NEXUS_CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
        ).split(",")
        if origin.strip()
    ]
    # A local workspace is also opened from other localhost ports (dev servers, the desktop app picks a free one), so
    # local mode accepts any localhost origin. A shared deployment lists its origins explicitly and gets no pattern.
    origin_pattern = os.environ.get("NEXUS_CORS_ORIGIN_REGEX") or (LOCAL_ORIGIN_PATTERN if local_mode_enabled() else None)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_origin_regex=origin_pattern,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept", "X-Nexus-API-Key", "X-Nexus-Tenant-ID", "X-Nexus-Workspace-ID"],
        expose_headers=["Content-Disposition"],
    )
    application.include_router(auth_router)
    application.include_router(billing_router)
    application.include_router(workflows.router)
    application.include_router(templates.router)
    application.include_router(teammates.router)
    application.include_router(approvals.router)
    application.include_router(sandboxes.router)
    application.include_router(knowledge.router)
    application.include_router(analytics.router)
    application.include_router(learning_transfer.router)
    application.include_router(architect.router)
    application.include_router(conversations.router)
    application.include_router(artifacts.router)
    application.include_router(self_healing.router)
    application.include_router(evolution.router)
    application.include_router(time_travel.router)
    application.include_router(providers.router)
    application.include_router(subscriptions.router)
    application.include_router(skills_tools.router)

    @application.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/ready", tags=["health"])
    async def ready() -> dict[str, str]:
        current: AppServices = application.state.services
        async with current.engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        await current.redis.ping()
        await current.qdrant.get_collections()
        return {"status": "ready"}

    return application


app = create_app()
