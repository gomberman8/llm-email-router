import asyncio

from fastapi import HTTPException

from app.config import settings

_semaphore = asyncio.Semaphore(settings.max_concurrent_runs)


async def acquire_semaphore():
    if _semaphore.locked():
        raise HTTPException(
            status_code=503,
            detail="Too many concurrent requests",
            headers={"Retry-After": str(settings.retry_after_seconds)},
        )
    await _semaphore.acquire()
    try:
        yield
    finally:
        _semaphore.release()
