"""One user of the shared test database at a time.

Agents run the suite on the same instance, and a reset in the middle of a run
drops the schema under it (2026-11-04: 50 false failures). A Postgres advisory
lock, held for the whole run, makes the second run or reset stop with a clear
message. The lock ends with the connection, so a killed run frees it.
"""
from __future__ import annotations

import asyncio
from typing import Any

import asyncpg

LOCK_KEY = 815_004_2026


class TestDatabaseBusy(RuntimeError):
    pass


class TestDatabaseLock:
    def __init__(self, database_url: str) -> None:
        self._dsn = database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
        self._loop = asyncio.new_event_loop()
        self._conn: Any = None

    def acquire(self) -> None:
        self._conn = self._loop.run_until_complete(asyncpg.connect(self._dsn))
        got = self._loop.run_until_complete(self._conn.fetchval("SELECT pg_try_advisory_lock($1)", LOCK_KEY))
        if not got:
            self.release()
            raise TestDatabaseBusy("another test run or reset is using the test database; wait for it to finish")

    def release(self) -> None:
        if self._conn is not None:
            self._loop.run_until_complete(self._conn.close())
            self._conn = None
        self._loop.close()
