#!/usr/bin/env python3
"""Bound unused Docker images to the approved limit (ECO-039; Marcelo, 2026-11-13).

Rule: unused images (no container, running or stopped, uses them) must stay at or
below UNUSED_IMAGE_LIMIT_BYTES, not counting protected images. When above, remove
unprotected unused images oldest first until within the limit. Never removed:
  * any image referenced by a container (running or stopped);
  * any image tagged (Metadata.LastTagTime, or Created when never tagged) in the
    last PROTECT_DAYS days -- e.g. pulled/tagged for a deploy whose container is
    not up yet;
  * release tags `forgehub-*:fh-*` and `*:rollback-*` created in the last
    PROTECT_DAYS days (the rollback point of recent deploys);
  * ForgeHub test-environment images (`forgehub-test-*`, or any `image:` of
    TEST_ENV_COMPOSE), whose services may simply be down;
  * volumes, containers or networks: only `docker image rm` on explicit tags/IDs
    is ever run -- no image prune with the all flag, no force flag.

"Unused size" is Docker's own accounting: the Images "Reclaimable" figure of
`docker system df` (decimal units) minus the unique size of the protected unused
images. The ECO-039 check imports measure() from this file, so both agree.

Usage: prune_unused_docker_images.py [--dry-run]
Called weekly by create_trash_cleanup_task.sh (job foundation-clear).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

UNUSED_IMAGE_LIMIT_BYTES = 10 * 10**9  # 10 GB, approved by Marcelo 2026-11-13
PROTECT_DAYS = 7
MAX_ROUNDS = 50
RM_TIMEOUT_SECONDS = 300
TEST_ENV_COMPOSE = Path("/root/project/forgehub/test-env/docker-compose.yml")

_UNITS = {"B": 1, "KB": 10**3, "MB": 10**6, "GB": 10**9, "TB": 10**12, "PB": 10**15}
_ZERO_TIME = "0001-01-01T00:00:00Z"


def parse_size(text: str) -> int:
    """Docker's human sizes ('10.53GB', '131.1kB', '0B') to bytes (decimal, as Docker prints them)."""
    match = re.match(r"\s*([0-9.]+)\s*([kKMGTP]?B)", text or "")
    if not match:
        raise ValueError(f"unparseable size {text!r}")
    return int(float(match.group(1)) * _UNITS[match.group(2).upper()])


def parse_time(text: str) -> datetime | None:
    text = (text or "").strip()
    if not text or text.startswith("0001-01-01"):
        return None
    # Python < 3.11 accepts at most 6 fractional digits; Docker prints 9.
    text = re.sub(r"(\.\d{6})\d+", r"\1", text.replace("Z", "+00:00"))
    return datetime.fromisoformat(text)


def docker(*args: str, timeout: int = 180) -> str:
    result = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"docker {' '.join(args[:2])} failed: {result.stderr.strip()[:300]}")
    return result.stdout


def reclaimable_bytes() -> int:
    for line in docker("system", "df", "--format", "{{json .}}").splitlines():
        row = json.loads(line)
        if row.get("Type") == "Images":
            return parse_size(row["Reclaimable"])
    raise RuntimeError("docker system df has no Images row")


def used_image_ids() -> set[str]:
    ids = docker("ps", "-aq", "--no-trunc").split()
    if not ids:
        return set()
    return set(docker("inspect", "--format", "{{.Image}}", *ids).split())


def compose_image_refs(path: Path = TEST_ENV_COMPOSE) -> set[str]:
    refs = set()
    text = path.read_text(errors="replace") if path.is_file() else ""
    for match in re.finditer(r"^\s*image:\s*['\"]?([^\s'\"#]+)", text, re.MULTILINE):
        ref = match.group(1)
        refs.add(ref if ":" in ref.rsplit("/", 1)[-1] else f"{ref}:latest")
    return refs


def _repo_name(ref: str) -> str:
    return ref.rpartition(":")[0].rsplit("/", 1)[-1]


def is_release_tag(ref: str) -> bool:
    tag = ref.rpartition(":")[2]
    return (_repo_name(ref).startswith("forgehub-") and tag.startswith("fh-")) or tag.startswith("rollback-")


def protection_reason(image: dict, now: datetime, compose_refs: set[str]) -> str | None:
    cutoff = now - timedelta(days=PROTECT_DAYS)
    if image["created"] >= cutoff and any(is_release_tag(ref) for ref in image["refs"]):
        return "recent release tag"
    if (image.get("last_tag") or image["created"]) >= cutoff:
        return "tagged in the last 7 days"
    if any(_repo_name(ref).startswith("forgehub-test-") or ref in compose_refs for ref in image["refs"]):
        return "ForgeHub test environment"
    return None


def inventory() -> dict[str, dict]:
    """One entry per image ID: refs, unique size, container count, creation and last-tag time."""
    data = json.loads(docker("system", "df", "-v", "--format", "{{json .}}"))
    images: dict[str, dict] = {}
    for row in data.get("Images") or []:
        for field in ("ID", "Repository", "Tag", "UniqueSize", "Containers"):
            if field not in row:
                raise RuntimeError(f"docker system df -v has no {field} field")
        entry = images.setdefault(row["ID"], {"id": row["ID"], "refs": [], "unique": 0, "containers": 0})
        if row["Repository"] not in ("", "<none>") and row["Tag"] not in ("", "<none>"):
            entry["refs"].append(f"{row['Repository']}:{row['Tag']}")
        try:
            entry["unique"] = max(entry["unique"], parse_size(row["UniqueSize"]))
        except ValueError:
            pass
        try:
            entry["containers"] = max(entry["containers"], int(row["Containers"] or 0))
        except ValueError:
            entry["containers"] = max(entry["containers"], 1)  # unknown: treat as used
    if images:
        fmt = "{{.Id}} {{.Created}} {{.Metadata.LastTagTime}}"
        for line in docker("image", "inspect", "--format", fmt, *images).splitlines():
            image_id, created, last_tag = (line.split(" ") + ["", ""])[:3]
            if image_id in images:
                images[image_id]["created"] = parse_time(created)
                images[image_id]["last_tag"] = parse_time(last_tag)
    return images


def classify(images: dict[str, dict], used: set[str], now: datetime,
             compose_refs: set[str]) -> tuple[list[dict], list[dict]]:
    """(removable oldest first, protected) among unused images."""
    removable, protected = [], []
    for image in images.values():
        if image["id"] in used or image["containers"]:
            continue
        if image.get("created") is None:
            image["reason"] = "unknown creation time"
            protected.append(image)
            continue
        image["reason"] = protection_reason(image, now, compose_refs)
        (protected if image["reason"] else removable).append(image)
    removable.sort(key=lambda image: image["created"])
    return removable, protected


def measure(now: datetime | None = None) -> dict:
    """Docker's reclaimable image bytes, minus the unique size of protected unused images."""
    now = now or datetime.now(timezone.utc)
    reclaimable = reclaimable_bytes()
    images = inventory()
    removable, protected = classify(images, used_image_ids(), now, compose_image_refs())
    protected_bytes = sum(image["unique"] for image in protected)
    return {"reclaimable": reclaimable, "protected_bytes": protected_bytes,
            "unused": max(0, reclaimable - protected_bytes),
            "removable": removable, "protected": protected}


def describe(image: dict) -> str:
    refs = ",".join(image["refs"]) or "<untagged>"
    return f"{image['id'][7:19]} {refs} created={image['created']:%Y-%m-%d} unique~{image['unique']/1e9:.2f}GB"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--dry-run", action="store_true", help="print what would be removed; remove nothing")
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    prefix = "[docker-image-prune]" + (" DRY-RUN" if args.dry_run else "")

    state = measure(now)
    start = state["unused"]
    print(f"{prefix} unused_images={state['unused']/1e9:.2f}GB (reclaimable {state['reclaimable']/1e9:.2f}GB "
          f"- protected {state['protected_bytes']/1e9:.2f}GB in {len(state['protected'])} images) "
          f"limit={UNUSED_IMAGE_LIMIT_BYTES/1e9:.0f}GB")
    attempted: set[str] = set()
    removed_count = 0
    for _ in range(MAX_ROUNDS):
        if state["unused"] <= UNUSED_IMAGE_LIMIT_BYTES:
            break
        removable = [image for image in state["removable"] if image["id"] not in attempted]
        if not removable:
            print(f"{prefix} WARNING no removable image left; still above limit")
            break
        # Oldest first until the (lower-bound) unique sizes cover the excess.
        excess, batch = state["unused"] - UNUSED_IMAGE_LIMIT_BYTES, []
        for image in removable:
            batch.append(image)
            if sum(item["unique"] for item in batch) >= excess:
                break
        for image in batch:
            attempted.add(image["id"])
            if args.dry_run:
                print(f"{prefix} would remove {describe(image)}")
                continue
            try:
                result = subprocess.run(["docker", "image", "rm", *(image["refs"] or [image["id"]])],
                                        capture_output=True, text=True, timeout=RM_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                print(f"{prefix} skip {describe(image)}: docker image rm timed out")
                continue
            if result.returncode:
                print(f"{prefix} skip {describe(image)}: {result.stderr.strip()[:200]}")
            else:
                removed_count += 1
                print(f"{prefix} removed {describe(image)}")
        if args.dry_run:
            freed = sum(image["unique"] for image in batch)
            print(f"{prefix} estimated freed>={freed/1e9:.2f}GB (a real run re-measures between batches)")
            break
        state = measure(now)
    if args.dry_run and state["unused"] <= UNUSED_IMAGE_LIMIT_BYTES:
        print(f"{prefix} within limit; nothing would be removed")
    if not args.dry_run:
        print(f"{prefix} removed={removed_count} unused_images {start/1e9:.2f}GB -> {state['unused']/1e9:.2f}GB")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, ValueError, OSError, subprocess.SubprocessError) as exc:
        print(f"[docker-image-prune] ERROR {exc}")
        sys.exit(1)
