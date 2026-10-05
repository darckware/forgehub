from app.core.config import CHAT_RESPONSE_LANGUAGE_NOTES, SUPPORTED_CHAT_RESPONSE_LANGUAGES, chat_response_language_allowed


def test_new_chat_language_choices_are_pt_en_es():
    assert SUPPORTED_CHAT_RESPONSE_LANGUAGES == ("pt-BR", "en", "es")
    for language in SUPPORTED_CHAT_RESPONSE_LANGUAGES:
        assert chat_response_language_allowed(language, "pt-BR")


def test_legacy_chat_language_can_be_preserved_but_not_newly_selected():
    assert "fr" in CHAT_RESPONSE_LANGUAGE_NOTES
    assert chat_response_language_allowed("fr", "fr")
    assert not chat_response_language_allowed("fr", "pt-BR")
    assert not chat_response_language_allowed("invalid", "invalid")
