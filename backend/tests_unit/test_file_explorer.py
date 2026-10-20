from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api.routes import file_explorer
from app.api.routes.file_explorer import _assert_not_root, _normalize
from app.core.deps import get_current_admin


def test_normalize_defaults_to_home_and_collapses_dot_segments():
    assert _normalize(None) == "/root"
    assert _normalize("  ") == "/root"
    assert _normalize("/root/project/../docs/./a.md") == "/root/docs/a.md"
    assert _normalize("/root//project/") == "/root/project"
    assert _normalize("/../..") == "/"


def test_normalize_rejects_relative_paths():
    with pytest.raises(HTTPException) as exc:
        _normalize("root/project")
    assert exc.value.status_code == 400


def test_filesystem_root_is_protected_from_changes():
    with pytest.raises(HTTPException):
        _assert_not_root("/")
    _assert_not_root("/root")


def test_every_route_requires_an_admin():
    # The Explorer is a root-level file manager (the terminal's counterpart):
    # "any logged-in user" must never be enough for any of its routes.
    for route in file_explorer.router.routes:
        deps = {d.call for d in route.dependant.dependencies}
        assert get_current_admin in deps, route.path
