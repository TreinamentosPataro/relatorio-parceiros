"""Minimal health endpoint without configuration disclosure."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["operational"])


class HealthResponse(BaseModel):
    """Public liveness response."""

    status: Literal["ok"] = "ok"


@router.get("/health", response_model=HealthResponse, include_in_schema=False)
def health() -> HealthResponse:
    """Report process liveness without checking or exposing dependencies."""

    return HealthResponse()
