from datetime import date
from types import SimpleNamespace

import pytest

from app.core import weather
from app.core.config import settings


class _Response:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "timezone": "America/Sao_Paulo",
            "daily": {
                "time": ["2030-01-10"], "weather_code": [61],
                "temperature_2m_max": [30.5], "temperature_2m_min": [22.0],
                "precipitation_sum": [4.2],
            },
            "current": {"temperature_2m": 25.0},
        }


class _Client:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def get(self, url, params):
        assert url == weather.OPEN_METEO_URL
        assert params["latitude"] == -22.9
        assert params["start_date"] == "2030-01-10"
        return _Response()


class _FallbackClient(_Client):
    async def get(self, url, params):
        assert url == weather.OPEN_METEO_URL
        assert params["latitude"] == weather.DEFAULT_WEATHER_LATITUDE
        assert params["longitude"] == weather.DEFAULT_WEATHER_LONGITUDE
        return _Response()


@pytest.mark.asyncio
async def test_open_meteo_weather_is_normalized(monkeypatch):
    monkeypatch.setattr(settings, "WEATHER_ENABLED", True)
    monkeypatch.setattr(settings, "WEATHER_LATITUDE", -22.9)
    monkeypatch.setattr(settings, "WEATHER_LONGITUDE", -43.2)
    monkeypatch.setattr(settings, "WEATHER_LOCATION", "Rio")
    monkeypatch.setattr(weather.httpx, "AsyncClient", _Client)

    result = await weather.get_weather(date(2030, 1, 10))

    assert result["condition"] == "chuva leve"
    assert result["temperature_min"] == 22.0
    assert weather.format_summary(result).startswith("🌤️ Tempo (Rio)")


@pytest.mark.asyncio
async def test_weather_uses_rio_fallback_without_gps(monkeypatch):
    monkeypatch.setattr(settings, "WEATHER_ENABLED", True)
    monkeypatch.setattr(settings, "WEATHER_LATITUDE", None)
    monkeypatch.setattr(settings, "WEATHER_LONGITUDE", None)
    monkeypatch.setattr(settings, "WEATHER_LOCATION", "")
    monkeypatch.setattr(weather.httpx, "AsyncClient", _FallbackClient)

    result = await weather.get_weather(date(2030, 1, 10))

    assert result["location"] == "Rio de Janeiro (RJ)"
    assert result["latitude"] == weather.DEFAULT_WEATHER_LATITUDE


class _LocationClient(_Client):
    async def get(self, url, params):
        assert (params["latitude"], params["longitude"]) == (-23.55, -46.63)
        return _Response()


@pytest.mark.asyncio
async def test_weather_prefers_the_stored_location(monkeypatch):
    monkeypatch.setattr(settings, "WEATHER_ENABLED", True)
    monkeypatch.setattr(settings, "WEATHER_LATITUDE", -22.9)
    monkeypatch.setattr(settings, "WEATHER_LONGITUDE", -43.2)
    monkeypatch.setattr(weather.httpx, "AsyncClient", _LocationClient)
    stored = SimpleNamespace(city="São Paulo", state="SP", latitude=-23.55, longitude=-46.63)

    result = await weather.get_weather(date(2030, 1, 10), stored)

    assert result["location"] == "São Paulo (SP)"
    assert (result["latitude"], result["longitude"]) == (-23.55, -46.63)
