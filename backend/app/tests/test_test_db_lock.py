"""Only one run or reset uses the shared test database at a time."""
import pytest

from app.core.config import settings
from app.scripts.test_db_lock import TestDatabaseBusy, TestDatabaseLock


def test_a_second_user_is_refused_while_the_suite_runs():
    with pytest.raises(TestDatabaseBusy):
        TestDatabaseLock(settings.DATABASE_URL).acquire()
