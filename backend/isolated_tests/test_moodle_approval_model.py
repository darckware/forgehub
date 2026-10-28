from app.db.models.moodle_approval import MoodleApproval, MoodleChallenge


def test_approval_is_bound_to_one_message_and_proposal():
    table = MoodleApproval.__table__
    assert table.c.message_id.unique
    assert table.c.request_id.unique
    assert not table.c.params_hash.nullable
    assert not table.c.source_agent_id.nullable
    assert not table.c.expires_at.nullable


def test_challenge_stores_only_digest_and_persistent_attempt_count():
    table = MoodleChallenge.__table__
    assert not table.c.secret_hash.nullable
    assert not table.c.attempts.nullable
    assert "secret" not in table.c
