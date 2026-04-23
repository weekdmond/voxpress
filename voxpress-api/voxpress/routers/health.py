from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from voxpress import __version__
from voxpress.db import get_session
from voxpress.runtime_settings import load_dashscope_runtime_settings
from voxpress.schemas import HealthOut

router = APIRouter()


@router.get("/api/health", response_model=HealthOut)
async def health(s: AsyncSession = Depends(get_session)) -> HealthOut:
    db_ok = True
    try:
        await s.execute(text("SELECT 1"))
    except Exception:
        db_ok = False
    dashscope_ok = False
    if db_ok:
        dashscope_ok = (await load_dashscope_runtime_settings(session=s)).enabled
    return HealthOut(ok=db_ok and dashscope_ok, version=__version__, ollama=dashscope_ok, whisper=dashscope_ok, db=db_ok)
