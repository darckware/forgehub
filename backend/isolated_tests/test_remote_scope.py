from types import SimpleNamespace
from app.core.remote_authority import delegation_covers


def test_empty_scope_never_authorizes():
    row = SimpleNamespace(servers=[], host_groups=[])
    assert not delegation_covers(row, 'A', set())


def test_machine_and_group_are_explicit():
    row = SimpleNamespace(servers=['A'], host_groups=['G'])
    assert delegation_covers(row, 'A', set())
    assert delegation_covers(row, 'B', {'G'})
    assert not delegation_covers(row, 'B', {'other'})
