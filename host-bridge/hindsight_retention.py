"""Bound Hindsight's active documents and keep a short recovery window.

The installed Hindsight 0.8.4 has no document TTL. This worker uses its
document API, writes extracted facts to the ForgeHub Knowledge Base, and
keeps a compressed source copy for 60 days before removing the source from
active recall. It never deletes a source unless both copies are verified.
"""

from __future__ import annotations

import argparse
import fcntl
import gzip
import hashlib
import json
import os
import tempfile
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ARCHIVE_ROOT = Path("/root/backup/hindsight-retention")
KNOWLEDGE_ROOT = Path("/root/.hermes/knowledge_base")
STATUS_PATH = ARCHIVE_ROOT / "status.json"
PROTECTED_TAGS = {"retention:keep", "retention:permanent"}


@dataclass(frozen=True)
class RetentionPolicy:
    review_days: int = 90
    compact_days: int = 180
    recovery_days: int = 60
    max_per_run: int = 100


def _instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def _write_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, name = tempfile.mkstemp(prefix=".hindsight-", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


class HindsightClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8888"):
        self.base_url = base_url.rstrip("/") + "/v1/default/banks"

    def _get(self, path: str, query: dict[str, Any] | None = None) -> dict:
        url = self.base_url + path
        if query:
            url += "?" + urllib.parse.urlencode(query)
        with urllib.request.urlopen(url, timeout=30) as response:
            return json.load(response)

    def banks(self) -> list[str]:
        return [item["bank_id"] for item in self._get("")["banks"]]

    def documents(self, bank: str) -> list[dict]:
        path = "/" + urllib.parse.quote(bank, safe="") + "/documents"
        items: list[dict] = []
        while True:
            page = self._get(path, {"limit": 200, "offset": len(items)})
            items.extend(page["items"])
            if not page["items"] or len(items) >= page["total"]:
                return items

    def document(self, bank: str, document_id: str) -> dict:
        return self._get("/" + urllib.parse.quote(bank, safe="") + "/documents/" + urllib.parse.quote(document_id, safe=""))

    def memories(self, bank: str, document_id: str) -> list[dict]:
        path = "/" + urllib.parse.quote(bank, safe="") + "/memories/list"
        items: list[dict] = []
        while True:
            page = self._get(path, {"document_id": document_id, "limit": 200, "offset": len(items)})
            items.extend(page["items"])
            if not page["items"] or len(items) >= page["total"]:
                return items

    def delete_document(self, bank: str, document_id: str) -> None:
        path = "/" + urllib.parse.quote(bank, safe="") + "/documents/" + urllib.parse.quote(document_id, safe="")
        request = urllib.request.Request(self.base_url + path, method="DELETE")
        with urllib.request.urlopen(request, timeout=30) as response:
            if response.status != 200:
                raise RuntimeError("Hindsight did not confirm document deletion")


class RetentionRunner:
    def __init__(
        self, client: HindsightClient, archive_root: Path, knowledge_root: Path,
        policy: RetentionPolicy, now: datetime | None = None,
    ):
        self.client = client
        self.archive_root = archive_root
        self.knowledge_root = knowledge_root
        self.policy = policy
        self.now = now or datetime.now(timezone.utc)

    def _paths(self, bank: str, item: dict) -> tuple[Path, Path, Path]:
        bank_slug = hashlib.sha256(bank.encode()).hexdigest()[:16]
        document_hash = hashlib.sha256(
            (bank + "\0" + item["id"] + "\0" + item["updated_at"]).encode()
        ).hexdigest()[:24]
        month = _instant(item["updated_at"]).strftime("%Y-%m")
        archive_dir = self.archive_root / bank_slug / month / document_hash
        note = self.knowledge_root / "share" / "hindsight" / "compactados" / bank_slug / month / f"{document_hash}.md"
        return archive_dir / "source.json.gz", archive_dir / "manifest.json", note

    def _compact(self, bank: str, item: dict) -> None:
        source_path, manifest_path, note_path = self._paths(bank, item)
        detail = self.client.document(bank, item["id"])
        if not detail.get("original_text"):
            raise RuntimeError("Document source text is unavailable for recovery")
        if (
            self.now - _instant(detail["updated_at"]) < timedelta(days=self.policy.compact_days)
            or PROTECTED_TAGS.intersection(detail.get("tags") or [])
        ):
            raise RuntimeError("Document changed since retention scan")
        if not source_path.exists():
            memories = self.client.memories(bank, item["id"])
            payload = json.dumps({"document": detail, "memories": memories}, ensure_ascii=False).encode()
            _write_atomic(source_path, gzip.compress(payload, compresslevel=9))
        with gzip.open(source_path, "rt", encoding="utf-8") as handle:
            archived = json.load(handle)
        if archived["document"]["id"] != item["id"]:
            raise RuntimeError("Archive verification failed")
        if (
            archived["document"]["updated_at"] != detail["updated_at"]
            or archived["document"].get("content_hash") != detail.get("content_hash")
        ):
            raise RuntimeError("Archived document is stale")

        if not note_path.exists():
            seen: set[str] = set()
            facts: list[str] = []
            for memory in archived["memories"]:
                if memory.get("state") == "invalidated" or memory.get("invalidated_at"):
                    continue
                fact = " ".join(str(memory.get("text") or "").split())
                key = fact.casefold()
                if fact and key not in seen:
                    seen.add(key)
                    facts.append(fact)
            if facts:
                lines = [
                    "# Hindsight: fatos compactados",
                    "",
                    "> Revisão pendente. Confirme fatos atuais antes de promovê-los a conhecimento permanente.",
                    "",
                    f"- Banco de origem: `{bank}`",
                    f"- Atualizado na origem: {_instant(item['updated_at']).date().isoformat()}",
                    f"- Arquivado em: {self.now.date().isoformat()}",
                    f"- Referência de origem: `{source_path.parent.name}`",
                    "",
                    "## Fatos extraídos",
                    "",
                    *(f"- {fact}" for fact in facts),
                    "",
                ]
                _write_atomic(note_path, "\n".join(lines).encode())
        if note_path.exists() and not note_path.read_text(encoding="utf-8").strip():
            raise RuntimeError("Knowledge Base note verification failed")

        if not manifest_path.exists():
            _write_atomic(manifest_path, json.dumps({
                "bank": bank, "document_id": item["id"],
                "archived_at": self.now.isoformat(), "deleted_at": None,
                "note_path": str(note_path) if note_path.exists() else None,
            }).encode())
        latest = self.client.document(bank, item["id"])
        if (
            latest["updated_at"] != detail["updated_at"]
            or latest.get("content_hash") != detail.get("content_hash")
            or PROTECTED_TAGS.intersection(latest.get("tags") or [])
        ):
            raise RuntimeError("Document changed before deletion")
        self.client.delete_document(bank, item["id"])
        manifest = json.loads(manifest_path.read_text())
        manifest["deleted_at"] = self.now.isoformat()
        _write_atomic(manifest_path, json.dumps(manifest).encode())

    def _discontinued_topics(self) -> list[Path]:
        root = self.knowledge_root / "share" / "hindsight" / "assuntos"
        topics = []
        for path in root.rglob("*.md"):
            if path.is_symlink() or not path.is_file():
                continue
            with path.open(encoding="utf-8") as handle:
                first = [handle.readline().strip().lower() for _ in range(20)]
            if first[0] != "---" or "---" not in first[1:]:
                continue
            header = first[1:first.index("---", 1)]
            if any(line in ("status: descontinuado", "status: discontinued") for line in header):
                topics.append(path)
        return topics

    def _discard_topic(self, path: Path) -> None:
        relative = path.relative_to(self.knowledge_root)
        digest = hashlib.sha256(str(relative).encode()).hexdigest()[:24]
        archive_dir = self.archive_root / "topics" / digest
        source_path = archive_dir / "source.md.gz"
        manifest_path = archive_dir / "manifest.json"
        content = path.read_bytes()
        if not source_path.exists():
            _write_atomic(source_path, gzip.compress(content, compresslevel=9))
        with gzip.open(source_path, "rb") as handle:
            if handle.read() != content:
                raise RuntimeError("Topic archive verification failed")
        if not manifest_path.exists():
            _write_atomic(manifest_path, json.dumps({
                "topic_path": str(relative), "archived_at": self.now.isoformat(),
            }).encode())
        if path.read_bytes() != content:
            raise RuntimeError("Topic changed before removal")
        path.unlink()

    def purge(self, now: datetime | None = None) -> int:
        now = now or self.now
        purged = 0
        for manifest_path in self.archive_root.glob("*/*/*/manifest.json"):
            manifest = json.loads(manifest_path.read_text())
            if not manifest.get("deleted_at"):
                continue
            if _instant(manifest["archived_at"]) + timedelta(days=self.policy.recovery_days) > now:
                continue
            if manifest.get("note_path") and not Path(manifest["note_path"]).is_file():
                continue
            source_path = manifest_path.with_name("source.json.gz")
            if source_path.exists():
                source_path.unlink()
                purged += 1
            manifest["purged_at"] = now.isoformat()
            manifest.pop("document_id", None)
            _write_atomic(manifest_path, json.dumps(manifest).encode())
        for manifest_path in (self.archive_root / "topics").glob("*/manifest.json"):
            manifest = json.loads(manifest_path.read_text())
            if _instant(manifest["archived_at"]) + timedelta(days=self.policy.recovery_days) > now:
                continue
            source_path = manifest_path.with_name("source.md.gz")
            if source_path.exists():
                source_path.unlink()
                purged += 1
            manifest["purged_at"] = now.isoformat()
            manifest.pop("topic_path", None)
            _write_atomic(manifest_path, json.dumps(manifest).encode())
        return purged

    def run(self, apply: bool = False) -> dict:
        report = {
            "checked_at": self.now.isoformat(), "review_days": self.policy.review_days,
            "compact_days": self.policy.compact_days, "recovery_days": self.policy.recovery_days,
            "mode": "apply" if apply else "preview", "total_documents": 0,
            "review_count": 0, "eligible_count": 0, "protected_count": 0,
            "compacted_count": 0, "purged_count": 0, "error_count": 0,
            "discontinued_topics_count": 0, "discarded_topics_count": 0,
        }
        candidates: list[tuple[str, dict]] = []
        for bank in self.client.banks():
            for item in self.client.documents(bank):
                report["total_documents"] += 1
                age = self.now - _instant(item["updated_at"])
                if age < timedelta(days=self.policy.review_days):
                    continue
                if PROTECTED_TAGS.intersection(item.get("tags") or []):
                    report["protected_count"] += 1
                elif age >= timedelta(days=self.policy.compact_days):
                    report["eligible_count"] += 1
                    candidates.append((bank, item))
                else:
                    report["review_count"] += 1
        topics = self._discontinued_topics()
        report["discontinued_topics_count"] = len(topics)
        if apply:
            candidates.sort(key=lambda pair: pair[1]["updated_at"])
            for bank, item in candidates[:self.policy.max_per_run]:
                try:
                    self._compact(bank, item)
                    report["compacted_count"] += 1
                except Exception:
                    # An incomplete archive or KB write must never delete a source.
                    report["error_count"] += 1
            for path in topics[:self.policy.max_per_run]:
                try:
                    self._discard_topic(path)
                    report["discarded_topics_count"] += 1
                except Exception:
                    report["error_count"] += 1
            report["purged_count"] = self.purge()
        _write_atomic(self.archive_root / "status.json", json.dumps(report).encode())
        return report


def read_status(path: Path = STATUS_PATH) -> dict | None:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Hindsight retention and KB compaction")
    parser.add_argument("mode", choices=("preview", "run"))
    args = parser.parse_args()
    ARCHIVE_ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (ARCHIVE_ROOT / "run.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        report = RetentionRunner(HindsightClient(), ARCHIVE_ROOT, KNOWLEDGE_ROOT, RetentionPolicy()).run(
            apply=args.mode == "run"
        )
    print(json.dumps(report))
    if report["error_count"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
