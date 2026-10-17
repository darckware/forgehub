"""Open-Meteo weather client for the personal domain.

Open-Meteo needs no API key. The client is deliberately small and stateless so a
failed provider never prevents the agenda or morning summary from working.
"""
from __future__ import annotations

from datetime import date
from typing import Any

import httpx

from app.core.config import settings

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


class WeatherError(RuntimeError):
    """Weather is unavailable or not configured."""


_CODES = {
    0: "céu limpo", 1: "predominantemente limpo", 2: "parcialmente nublado", 3: "nublado",
    45: "névoa", 48: "névoa congelante", 51: "garoa leve", 53: "garoa", 55: "garoa forte",
    56: "garoa congelante leve", 57: "garoa congelante forte", 61: "chuva leve", 63: "chuva",
    65: "chuva forte", 66: "chuva congelante leve", 67: "chuva congelante forte",
    71: "neve leve", 73: "neve", 75: "neve forte", 77: "grãos de neve", 80: "pancadas leves",
    81: "pancadas", 82: "pancadas fortes", 85: "pancadas de neve leves", 86: "pancadas de neve fortes",
    95: "trovoada", 96: "trovoada com granizo leve", 99: "trovoada com granizo forte",
}


def describe_code(code: int | None) -> str:
    return _CODES.get(code, "condição desconhecida")


def _params(day: date | None) -> dict[str, Any]:
    if settings.WEATHER_LATITUDE is None or settings.WEATHER_LONGITUDE is None:
        raise WeatherError("weather location is not configured")
    params: dict[str, Any] = {
        "latitude": settings.WEATHER_LATITUDE, "longitude": settings.WEATHER_LONGITUDE,
        "timezone": settings.WEATHER_TIMEZONE,
        "current": "temperature_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum",
        "forecast_days": 7,
    }
    if day:
        params["start_date"] = day.isoformat()
        params["end_date"] = day.isoformat()
    return params


async def get_weather(day: date | None = None) -> dict[str, Any]:
    """Return normalized current and daily forecast data for the configured location."""
    if not settings.WEATHER_ENABLED:
        raise WeatherError("weather is disabled")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(settings.WEATHER_API_URL or OPEN_METEO_URL, params=_params(day))
            response.raise_for_status()
            raw = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise WeatherError("weather provider unavailable") from exc
    current = raw.get("current") or {}
    daily = raw.get("daily") or {}
    dates = daily.get("time") or []
    index = 0
    if day and day.isoformat() in dates:
        index = dates.index(day.isoformat())
    return {
        "location": settings.WEATHER_LOCATION,
        "latitude": settings.WEATHER_LATITUDE,
        "longitude": settings.WEATHER_LONGITUDE,
        "timezone": raw.get("timezone", settings.WEATHER_TIMEZONE),
        "date": dates[index] if dates else (day.isoformat() if day else None),
        "condition": describe_code((daily.get("weather_code") or [None])[index]),
        "weather_code": (daily.get("weather_code") or [None])[index],
        "current_condition": describe_code(current.get("weather_code")),
        "current_temperature": current.get("temperature_2m"),
        "temperature_max": (daily.get("temperature_2m_max") or [None])[index],
        "temperature_min": (daily.get("temperature_2m_min") or [None])[index],
        "precipitation_sum": (daily.get("precipitation_sum") or [None])[index],
        "current": current,
    }


def format_summary(weather: dict[str, Any]) -> str:
    """Compact Portuguese line suitable for the morning summary."""
    current = weather.get("current_temperature")
    current_text = (f"agora {current}°C, " if current is not None else "")
    current_condition = weather.get("current_condition")
    if current_condition:
        current_text += f"{current_condition}, "
    return (f"🌤️ Tempo ({weather['location']}): {current_text}{weather['condition']}, "
            f"{weather['temperature_min']}–{weather['temperature_max']}°C, "
            f"chuva prevista {weather['precipitation_sum']} mm.")
