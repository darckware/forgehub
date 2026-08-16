"""Unit coverage for the ai-draft reply parser -- the part with real failure
modes (an agent's raw text reply, not a typed object)."""
import pytest
from fastapi import HTTPException

from app.core.ai_draft import parse_ai_draft_reply


def test_parse_fenced_json():
    reply = (
        "Aqui está o rascunho:\n\n"
        '```json\n{"items": [{"title": "Login", "item_type": "feature", '
        '"description": null, "priority": "high"}]}\n```\n'
    )
    draft = parse_ai_draft_reply(reply, "planning_items")
    assert draft["items"][0]["title"] == "Login"


def test_parse_tolerates_trailing_prose_without_fence():
    # Regression: an agent reply with a valid JSON object NOT wrapped in a
    # fence, followed by a closing remark, used to fail json.loads with
    # "Extra data" -- raw_decode must ignore the trailing text instead.
    reply = '{"items": [{"title": "Login", "item_type": "feature"}]} Espero que ajude!'
    draft = parse_ai_draft_reply(reply, "planning_items")
    assert draft["items"][0]["title"] == "Login"


def test_parse_rejects_malformed_json():
    with pytest.raises(HTTPException) as exc:
        parse_ai_draft_reply("isso não é json nenhum", "planning_items")
    assert exc.value.status_code == 502


def test_parse_rejects_shape_mismatch():
    reply = '```json\n{"wrong_key": []}\n```'
    with pytest.raises(HTTPException) as exc:
        parse_ai_draft_reply(reply, "planning_items")
    assert exc.value.status_code == 502


def test_parse_context_summary():
    reply = '```json\n{"summary": "Resumo denso do documento enviado."}\n```'
    draft = parse_ai_draft_reply(reply, "context_summary")
    assert draft["summary"] == "Resumo denso do documento enviado."
