import io
import json

import pytest

from app.api.routes import moodle_approval


class Response(io.BytesIO):
    status = 200


def test_confirmation_link_uses_maia_home_channel_without_bot_credentials(monkeypatch):
    seen = []
    monkeypatch.setattr(moodle_approval.settings, 'CHAT_BRIDGE_URL', 'http://bridge.local:8910')
    monkeypatch.setattr(moodle_approval.settings, 'CHAT_BRIDGE_TOKEN', 'bridge-fixture')
    monkeypatch.setattr(moodle_approval.settings, 'MOODLE_APPROVAL_TELEGRAM_CHAT_ID', '123456789')
    def open_request(request, timeout):
        seen.append(request)
        return Response(b'{"success":true}')
    monkeypatch.setattr(moodle_approval, 'urlopen', open_request)
    moodle_approval._send_telegram('Link: https://example.test/#telegram_challenge=fixture')
    assert seen[0].full_url == 'http://bridge.local:8910/v1/messages/send'
    assert seen[0].get_header('X-bridge-token') == 'bridge-fixture'
    assert json.loads(seen[0].data) == {
        'profile': 'maia', 'target': 'telegram:123456789',
        'message': 'Link: https://example.test/#telegram_challenge=fixture',
    }


def test_skipped_delivery_is_not_treated_as_sent(monkeypatch):
    monkeypatch.setattr(moodle_approval.settings, 'MOODLE_APPROVAL_TELEGRAM_CHAT_ID', '123456789')
    monkeypatch.setattr(moodle_approval, 'urlopen', lambda *args, **kwargs: Response(b'{"skipped":true}'))
    with pytest.raises(ValueError):
        moodle_approval._send_telegram('fixture')


def test_rejects_non_private_chat_destination(monkeypatch):
    monkeypatch.setattr(moodle_approval.settings, 'MOODLE_APPROVAL_TELEGRAM_CHAT_ID', '-100123')
    with pytest.raises(ValueError):
        moodle_approval._send_telegram('fixture')
