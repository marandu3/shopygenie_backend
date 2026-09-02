from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import AsyncSessionLocal

# Mutable indirection so code that can't use FastAPI's Depends() override
# mechanism — background tasks, in particular — still gets the correct
# loop-bound session factory in tests. Tests bind their own engine per test
# function (asyncpg connections are event-loop bound); see tests/conftest.py
# db fixture, which reassigns this alongside app.dependency_overrides[get_db].
_session_factory = AsyncSessionLocal


def set_session_factory(factory) -> None:
    global _session_factory
    _session_factory = factory


def get_session_factory():
    return _session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with _session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
