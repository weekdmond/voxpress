from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from voxpress import __version__
from voxpress.config import settings
from voxpress.db import get_session
from voxpress.schemas import HealthOut

router = APIRouter()


@router.get("/api/health", response_model=HealthOut)
async def health(s: AsyncSession = Depends(get_session)) -> HealthOut:
    db_ok = True
    try:
        await s.execute(text("SELECT 1"))
    except Exception:
        db_ok = False
    dashscope_ok = settings.dashscope_enabled
    return HealthOut(ok=db_ok and dashscope_ok, version=__version__, ollama=dashscope_ok, whisper=dashscope_ok, db=db_ok)
