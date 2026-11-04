from app.db.models.profile import MODULES


def test_menu_modules_are_available_for_permissions():
    assert {"demands", "docs", "auditor", "servers", "system_control"} <= set(MODULES)
