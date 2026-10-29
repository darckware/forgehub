"""Values a `Settings(ENVIRONMENT="test", ...)` built in a unit test needs to
pass the T.3 integration/credential check: stub URLs and fresh random
credentials (never equal to a production secret). Tests about something
else -- the database guard, the background loops -- merge these in so they
keep testing only their own rule."""
import secrets

STUB_ORIGIN = "http://127.0.0.1:8003"


def safe_test_integration_values(origin: str = STUB_ORIGIN) -> dict[str, str]:
    return {
        "JWT_SECRET": secrets.token_hex(32),
        "CHAT_BRIDGE_TOKEN": secrets.token_hex(32),
        "SECRETS_ENCRYPTION_KEY": secrets.token_hex(32),
        "AGENT_ACTIVITY_WEBHOOK_SECRET": secrets.token_hex(32),
        "DARCKWARE_AGENT_TOKEN": secrets.token_hex(32),
        "DARCKWARE_APPROVER_TOKEN": secrets.token_hex(32),
        "DARCKWARE_AGENT_TOKEN_FILE": "",
        "RECAPTCHA_SECRET_KEY": "",
        "FORGEROUTER_SSO_SECRET": "",
        "CHAT_BRIDGE_URL": origin,
        "DARCKWARE_API_URL": f"{origin}/darckware",
        "FORGEROUTER_URL": f"{origin}/forgerouter",
        "TAILSCALE_API_URL": f"{origin}/tailscale",
        "WEATHER_API_URL": f"{origin}/weather",
        "WEATHER_REVERSE_GEOCODE_URL": f"{origin}/weather",
    }
