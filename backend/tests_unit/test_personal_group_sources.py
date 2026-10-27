import json
import pytest
from app.mcp.personal_group_sources import GroupSourceError, message_reference, monitored_group, observed_message

CHAT='120363000000000123@g.us'
@pytest.fixture
def group_root(tmp_path):
    (tmp_path/'_monitoramento.json').write_text(json.dumps({'enabled':[CHAT]}))
    (tmp_path/'_grupos.json').write_text(json.dumps({CHAT:{'nome':'Grupo sintético','ultimo_ts':1000}}))
    row={'ts':1000.0,'quando':'2026-10-27T10:00:00Z','chat':CHAT,'grupo':'Grupo sintético','autor':'Participante fictício','texto':'Mensagem de teste'}
    (tmp_path/'120363000000000123.jsonl').write_text(json.dumps(row)+'\n')
    return tmp_path,row

def test_message_reference_is_stable_and_verifiable(group_root):
    root,row=group_root
    ref=message_reference(CHAT,row)
    assert ref==message_reference(CHAT,dict(reversed(list(row.items()))))
    assert observed_message(root,CHAT,ref)['texto']=='Mensagem de teste'
    with pytest.raises(GroupSourceError):observed_message(root,CHAT,'0'*64)

def test_only_monitored_observed_groups_can_register(group_root):
    root,_=group_root
    assert monitored_group(root,CHAT)['name']=='Grupo sintético'
    with pytest.raises(GroupSourceError):monitored_group(root,'123@g.us')
    (root/'_monitoramento.json').write_text('{"enabled":[]}')
    with pytest.raises(GroupSourceError):monitored_group(root,CHAT)

@pytest.mark.parametrize('bad',['../_monitoramento','../../a@g.us','1@g.us/../x','unknown'])
def test_group_path_cannot_escape_inventory(group_root,bad):
    root,_=group_root
    with pytest.raises(GroupSourceError):monitored_group(root,bad)

def test_missing_source_and_symlink_are_not_authorization(group_root,tmp_path):
    root,row=group_root
    (root/'_monitoramento.json').unlink()
    with pytest.raises(GroupSourceError):monitored_group(root,CHAT)
    (root/'_monitoramento.json').write_text(json.dumps({'enabled':[CHAT]}))
    path=root/'120363000000000123.jsonl';path.unlink()
    outside=root.parent/'outside.jsonl';outside.write_text(json.dumps(row))
    path.symlink_to(outside)
    with pytest.raises(GroupSourceError):observed_message(root,CHAT,message_reference(CHAT,row))
