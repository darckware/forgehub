"""Retention keeps a recoverable source while moving durable facts to the KB."""

import gzip
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hindsight_retention import RetentionPolicy, RetentionRunner


NOW = datetime(2026, 10, 2, tzinfo=timezone.utc)


class FakeClient:
    def __init__(self, documents):
        self.items = {item["id"]: item for item in documents}
        self.deleted = []
        self.changed_at_read = False
        self.fail_delete = False

    def banks(self):
        return ["hermes"]

    def documents(self, _bank):
        return list(self.items.values())

    def document(self, _bank, document_id):
        item = self.items[document_id]
        if self.changed_at_read:
            item = {**item, "updated_at": NOW.isoformat()}
        return {**item, "original_text": "Original private conversation"}

    def memories(self, _bank, document_id):
        return [
            {"text": "The project uses PostgreSQL.", "state": "active"},
            {"text": "The project uses PostgreSQL.", "state": "active"},
            {"text": "Obsolete fact", "state": "invalidated"},
        ] if document_id == "old" else []

    def delete_document(self, _bank, document_id):
        if self.fail_delete:
            raise RuntimeError("simulated API failure")
        self.deleted.append(document_id)
        del self.items[document_id]


def doc(document_id, age_days, *, tags=None):
    return {
        "id": document_id,
        "updated_at": (NOW - timedelta(days=age_days)).isoformat(),
        "created_at": (NOW - timedelta(days=age_days + 1)).isoformat(),
        "tags": tags or [],
        "memory_unit_count": 2,
    }


def test_preview_counts_review_and_compaction_without_deleting(tmp_path):
    client = FakeClient([doc("recent", 30), doc("review", 100), doc("old", 181),
                         doc("keep", 250, tags=["retention:permanent"])])
    runner = RetentionRunner(client, tmp_path / "archive", tmp_path / "kb", RetentionPolicy(), NOW)

    report = runner.run(apply=False)

    assert report["review_count"] == 1
    assert report["eligible_count"] == 1
    assert report["protected_count"] == 1
    assert report["compacted_count"] == 0
    assert client.deleted == []
    assert not list((tmp_path / "kb").rglob("*.md"))


def test_apply_archives_then_writes_deduplicated_facts_and_deletes(tmp_path):
    client = FakeClient([doc("old", 181)])
    archive = tmp_path / "archive"
    kb = tmp_path / "kb"
    runner = RetentionRunner(client, archive, kb, RetentionPolicy(), NOW)

    report = runner.run(apply=True)

    assert report["compacted_count"] == 1
    assert client.deleted == ["old"]
    note_path = next(kb.rglob("*.md"))
    assert "share/hindsight/compactados" in str(note_path)
    note = note_path.read_text()
    assert note.count("The project uses PostgreSQL.") == 1
    assert "Obsolete fact" not in note
    assert "Original private conversation" not in note
    source = next(archive.rglob("*.json.gz"))
    with gzip.open(source, "rt") as handle:
        assert json.load(handle)["document"]["original_text"] == "Original private conversation"


def test_purge_waits_60_days_and_keeps_kb_note(tmp_path):
    client = FakeClient([doc("old", 181)])
    runner = RetentionRunner(client, tmp_path / "archive", tmp_path / "kb", RetentionPolicy(), NOW)
    runner.run(apply=True)
    assert runner.purge(NOW + timedelta(days=59)) == 0
    assert runner.purge(NOW + timedelta(days=61)) == 1
    assert not list((tmp_path / "archive").rglob("*.json.gz"))
    assert list((tmp_path / "kb").rglob("*.md"))


def test_updated_document_is_never_removed_from_stale_scan(tmp_path):
    client = FakeClient([doc("old", 181)])
    client.changed_at_read = True
    runner = RetentionRunner(client, tmp_path / "archive", tmp_path / "kb", RetentionPolicy(), NOW)

    report = runner.run(apply=True)

    assert report["compacted_count"] == 0
    assert client.deleted == []
    assert not list((tmp_path / "archive").rglob("*.json.gz"))


def test_purge_keeps_source_if_knowledge_note_disappears(tmp_path):
    client = FakeClient([doc("old", 181)])
    runner = RetentionRunner(client, tmp_path / "archive", tmp_path / "kb", RetentionPolicy(), NOW)
    runner.run(apply=True)
    next((tmp_path / "kb").rglob("*.md")).unlink()

    assert runner.purge(NOW + timedelta(days=61)) == 0
    assert list((tmp_path / "archive").rglob("*.json.gz"))


def test_delete_failure_keeps_archive_and_original_for_retry(tmp_path):
    client = FakeClient([doc("old", 181)])
    client.fail_delete = True
    runner = RetentionRunner(client, tmp_path / "archive", tmp_path / "kb", RetentionPolicy(), NOW)

    first = runner.run(apply=True)

    assert first["error_count"] == 1
    assert "old" in client.items
    assert list((tmp_path / "archive").rglob("*.json.gz"))
    client.fail_delete = False
    second = runner.run(apply=True)
    assert second["compacted_count"] == 1
    assert client.deleted == ["old"]


def test_discontinued_subject_leaves_kb_then_backup_expires(tmp_path):
    kb = tmp_path / "kb"
    topic = kb / "share" / "hindsight" / "assuntos" / "projetos" / "antigo.md"
    topic.parent.mkdir(parents=True)
    topic.write_text("---\nstatus: descontinuado\n---\n# Assunto antigo\n", encoding="utf-8")
    runner = RetentionRunner(FakeClient([]), tmp_path / "archive", kb, RetentionPolicy(), NOW)

    preview = runner.run(apply=False)
    assert preview["discontinued_topics_count"] == 1
    assert topic.exists()

    applied = runner.run(apply=True)
    assert applied["discarded_topics_count"] == 1
    assert not topic.exists()
    assert list((tmp_path / "archive" / "topics").rglob("*.gz"))
    assert runner.purge(NOW + timedelta(days=61)) == 1
    assert not list((tmp_path / "archive" / "topics").rglob("*.gz"))
