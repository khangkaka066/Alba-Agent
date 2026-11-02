"""Shared request dependencies and scoped route helpers."""

from __future__ import annotations

from typing import Any, cast

from fastapi import HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncEngine

from app.services import AppServices


def get_services(request: Request) -> AppServices:
    return cast(AppServices, request.app.state.services)


def not_found(message: str = "Resource is not visible in this workspace") -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, message)


def conflict(message: str) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, message)
