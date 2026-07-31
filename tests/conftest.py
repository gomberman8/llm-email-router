import asyncio
import os

import pytest
from pydantic_ai import models

os.environ["WARMUP_ON_STARTUP"] = "false"
models.ALLOW_MODEL_REQUESTS = False


@pytest.fixture
def saturated_semaphore():
    from app.config import settings
    from app.guards import _semaphore

    async def _acquire_all() -> None:
        for _ in range(settings.max_concurrent_runs):
            await _semaphore.acquire()

    asyncio.run(_acquire_all())
    yield
    for _ in range(settings.max_concurrent_runs):
        _semaphore.release()
