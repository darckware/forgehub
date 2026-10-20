"""Sync must flag registered scripts that vanished from disk.

Pure-function test on purpose: the test DB is the production catalog, and a
real sync against a temp profiles dir would flag every real row as missing.
"""
from app.api.routes.cron_scripts import _mark_missing
from app.db.models.cron_script import CronScript


def _row(name: str, exists: bool = True) -> CronScript:
    return CronScript(name=name, location="athos", path=f"/profiles/athos/scripts/{name}", exists_on_disk=exists)


def test_mark_missing_flags_only_registered_rows_the_scan_no_longer_finds():
    present, gone, already_gone = _row("backup_hermes_root.sh"), _row("worker.sh"), _row("old.sh", exists=False)

    changed = _mark_missing([present, gone, already_gone], {"backup_hermes_root.sh"})

    assert changed == [gone]
    assert gone.exists_on_disk is False
    assert present.exists_on_disk is True
    # The row is kept (it's the record of what the script was), only flagged.
    assert gone.name == "worker.sh"


def test_mark_missing_is_idempotent():
    gone = _row("worker.sh")
    _mark_missing([gone], set())
    assert _mark_missing([gone], set()) == []
