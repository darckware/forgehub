"""An arbitrary minimum count is not evidence of canonical catalog coverage."""
import importlib.util
import json
from pathlib import Path
import sys

SPEC = importlib.util.spec_from_file_location('catalog_verifier', Path(__file__).parents[1] / 'checklist_verifier.py')
v = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = v
SPEC.loader.exec_module(v)


def setup(monkeypatch, tmp_path, foundation, company):
    source = tmp_path/'catalog.py'
    source.write_text("_CHECK_ROWS = (('ECO-001','a','athos','d',55,True), ('ECO-061','a','athos','d',55,True))\nRETIRED_AUDIT_CHECKS = {'ECO-021': 'retired'}\n")
    monkeypatch.setattr(v, 'CATALOG_SOURCE', source)
    foundation = [row if isinstance(row,dict) else {'name':row,'status':'retired' if row=='ECO-021' else 'ok'} for row in foundation]
    company = [row if isinstance(row,dict) else {'name':row,'enabled':row!='ECO-021'} for row in company]
    monkeypatch.setattr(v, 'psql', lambda *args: json.dumps(foundation if args[1]=='foundation' else company))


def test_extra_checks_do_not_hide_missing_required_module(monkeypatch, tmp_path):
    setup(monkeypatch,tmp_path,['ECO-001','ECO-002','ECO-003'],['ECO-001','ECO-061'])
    result = v.check_audit_tables()
    assert not result.ok
    assert 'ECO-061' in result.notes


def test_exact_required_ids_with_retired_row_preserved_pass(monkeypatch,tmp_path):
    setup(monkeypatch,tmp_path,['ECO-001','ECO-061','ECO-021'],['ECO-001','ECO-061','ECO-021'])
    assert v.check_audit_tables().ok


def test_duplicate_foundation_control_fails(monkeypatch,tmp_path):
    setup(monkeypatch,tmp_path,['ECO-001','ECO-061','ECO-061'],['ECO-001','ECO-061'])
    assert not v.check_audit_tables().ok


def test_required_company_control_cannot_be_silently_disabled(monkeypatch,tmp_path):
    setup(monkeypatch,tmp_path,['ECO-001','ECO-061'],['ECO-001',{'name':'ECO-061','enabled':False}])
    result = v.check_audit_tables()
    assert not result.ok
    assert 'activation mismatch' in result.notes


def test_required_foundation_control_cannot_be_retired(monkeypatch,tmp_path):
    setup(monkeypatch,tmp_path,['ECO-001',{'name':'ECO-061','status':'retired'}],['ECO-001','ECO-061'])
    result = v.check_audit_tables()
    assert not result.ok
    assert 'activation mismatch' in result.notes
