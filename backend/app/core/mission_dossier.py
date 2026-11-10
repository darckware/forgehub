"""Verify dossier bytes in the existing project-scoped Docs tree."""
import asyncio
import hashlib
import os
import stat

from app.core import mission_documents
from app.db.models.artifact import ArtifactVersion
from app.db.models.project import Project

MAX_DOSSIER_BYTES = 8 * 1024 * 1024


class DossierUnverifiable(ValueError):
    pass


def _digest(project, location):
    try:
        path = mission_documents.check_doc_path(mission_documents.MISSION_DOCS_ROOT, location,
            mission_documents.allowed_prefixes(project.name, project.project_type))
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_DOSSIER_BYTES:
                raise DossierUnverifiable("Dossier must be a regular document of at most 8 MiB")
            data = handle.read(MAX_DOSSIER_BYTES + 1)
            if len(data) > MAX_DOSSIER_BYTES:
                raise DossierUnverifiable("Dossier exceeds 8 MiB")
            return hashlib.sha256(data).hexdigest()
    except (OSError, mission_documents.DocPathRefused) as exc:
        raise DossierUnverifiable("Dossier file is unavailable in this mission's document folder") from exc


async def verify_dossier(db, project_id, artifact_version_id, expected_hash):
    project = await db.get(Project, project_id, populate_existing=True)
    version = await db.get(ArtifactVersion, artifact_version_id, populate_existing=True)
    if project is None or version is None:
        raise DossierUnverifiable("Dossier project or artifact version is unavailable")
    recorded = (version.checksum or "").strip().lower().removeprefix("sha256:")
    if recorded != expected_hash.lower():
        raise DossierUnverifiable("Dossier requires a matching recorded SHA-256")
    actual = await asyncio.to_thread(_digest, project, version.location_uri)
    return actual == expected_hash.lower()
