import json
import pytest
from app.mcp import personal_groups as pg
from app.mcp import personal_contacts as pc

CHAT='120363000000000123@g.us'

def test_group_read_returns_real_reference_and_capture_uses_it(tmp_path,monkeypatch):
    monkeypatch.setattr(pg,'GRUPOS',tmp_path);monkeypatch.setattr(pg,'MONITORAMENTO',tmp_path/'_monitoramento.json')
    (tmp_path/'_monitoramento.json').write_text(json.dumps({'enabled':[CHAT]}))
    (tmp_path/'_grupos.json').write_text(json.dumps({CHAT:{'nome':'Grupo fictício'}}))
    record={'ts':1000,'chat':CHAT,'autor':'Pessoa fictícia','texto':'Texto fictício','quando':'2026-10-27'}
    (tmp_path/'120363000000000123.jsonl').write_text(json.dumps(record)+'\n')
    read=pg.group_messages('Grupo fictício',agora=1001)
    assert read['grupo_id']==CHAT
    reference=read['mensagens'][0]['mensagem_ref']
    calls=[]
    def api(method,path,body):
        calls.append((method,path,body));return {'id':'11111111-1111-4111-8111-111111111111','status':'pending','group_name':'Grupo fictício'}
    captured=pg.capture_suggestion('Grupo fictício',reference,'Demanda fictícia',api_call=api)
    assert captured['sugestao']['id']=='11111111-1111-4111-8111-111111111111'
    assert calls[0][2]['whatsapp_id']==CHAT and calls[0][2]['message_ref']==reference
    with pytest.raises(pg.GroupError):pg.capture_suggestion('Desconhecido',reference,'Demanda',api_call=api)


def test_pending_group_suggestions_are_not_formatted_as_contacts(monkeypatch):
    monkeypatch.setattr(pc,'_call',lambda *a,**k:[{'id':'real-uuid','kind':'demand','title':'Teste','details':'','contact_name':'','contact_phone':'','source_kind':'group','group_name':'Grupo fictício','group_id':'group-uuid','source_author':'Pessoa fictícia','source_message_ref':'a'*64}])
    item=pc.list_suggestions()[0]
    assert item['origem']=='grupo' and item['grupo']=='Grupo fictício'
    assert item['autor']=='Pessoa fictícia'
