#!/usr/bin/env python3
"""Read-only voice runtime audit for the principal Hermes profiles (Athos).

Implements Foundation 52_policies/telegram-audio-ptbr.md. --channel telegram (ForgeHub
Auditor ECO-040): every profile with a Telegram bot has the canonical STT/TTS/voice settings,
FFmpeg is available and the profile's Telegram adapter is connected in the multiplex gateway.
--channel cli (ECO-041): every principal profile has the canonical settings plus the CLI
recording dependencies (arecord or parec) and push-to-talk key. --skip-tts-probe skips looking
for the Piper pt-BR voice model. Never prints tokens or credentials. Exit 0 = contract passed.

Rebuilt 2026-09-27: the original was lost when the cron scripts were moved out of
profiles/athos/scripts on 2026-09-21 and no backup kept it.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import yaml

HERMES = Path("/root/.hermes")
PROFILES = HERMES / "profiles"
CORE_PROFILES = ("athos", "aegis", "daedalus", "hephaestus", "atlas", "mnemosyne", "scriba", "themis", "kairos", "lara", "maia")
# Dated voice policy (2026-10-01) supersedes the original uniform Piper
# template. In particular, Lara/Maia keep female pt-BR Edge voices.
EDGE_VOICES = {
    'athos': 'pt-BR-AntonioNeural', 'aegis': 'pt-BR-AntonioNeural',
    'kairos': 'pt-BR-AntonioNeural', 'lara': 'pt-BR-FranciscaNeural',
    'maia': 'pt-BR-FranciscaNeural',
}
CANONICAL = {
    ("stt", "enabled"): True,
    ("stt", "provider"): "local",
    ("stt", "local", "model"): "base",
    ("stt", "local", "language"): "pt",
    ("tts", "provider"): "piper",
    ("tts", "piper", "voice"): "pt_BR-jeff-medium",
    ("voice", "auto_tts"): False,
}
PIPER_VOICE = "pt_BR-jeff-medium"


def get(config: dict, keys: tuple[str, ...]):
    node = config
    for key in keys:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


def has_telegram_bot(profile: str) -> bool:
    env = PROFILES / profile / ".env"
    try:
        return any(line.startswith("TELEGRAM_BOT_TOKEN=") and line.split("=", 1)[1].strip()
                   for line in env.read_text(errors="replace").splitlines())
    except OSError:
        return False


def settings_drift(profile: str) -> list[str]:
    try:
        config = yaml.safe_load((PROFILES / profile / "config.yaml").read_text()) or {}
    except Exception as exc:  # noqa: BLE001
        return [f"config.yaml unreadable: {exc.__class__.__name__}"]
    expected = dict(CANONICAL)
    if profile in EDGE_VOICES:
        expected.pop(('tts', 'piper', 'voice'))
        expected.update({('stt', 'local', 'model'): 'large-v3-turbo',
                         ('tts', 'provider'): 'edge',
                         ('tts', 'edge', 'voice'): EDGE_VOICES[profile]})
    return [f"{'.'.join(k)}={get(config, k)!r} (expected {v!r})" for k, v in expected.items() if get(config, k) != v]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--channel", choices=("telegram", "cli"), required=True)
    parser.add_argument("--skip-tts-probe", action="store_true")
    args = parser.parse_args()

    active = [p for p in CORE_PROFILES if (PROFILES / p).is_dir() and not (PROFILES / p / "gateway.parked").exists()]
    profiles = [p for p in active if has_telegram_bot(p)] if args.channel == "telegram" else active
    problems: list[str] = []

    if not shutil.which("ffmpeg"):
        problems.append("ffmpeg not installed (voice conversion)")
    if args.channel == "cli" and not (shutil.which("arecord") or shutil.which("parec")):
        problems.append("no recorder: install arecord (alsa-utils) or parec (pulseaudio-utils)")
    if not args.skip_tts_probe and any(p not in EDGE_VOICES for p in profiles):
        voices = [p for p in HERMES.rglob(f"{PIPER_VOICE}*.onnx")] if HERMES.is_dir() else []
        if not voices:
            problems.append(f"Piper voice model {PIPER_VOICE} not found under {HERMES}")

    platforms: dict = {}
    if args.channel == "telegram":
        try:
            state = json.loads((HERMES / "gateway_state.json").read_text())
            platforms = state.get("platforms") or {}
        except Exception as exc:  # noqa: BLE001
            problems.append(f"gateway_state.json unreadable: {exc.__class__.__name__}")

    for profile in profiles:
        drift = settings_drift(profile)
        if args.channel == "cli":
            config = yaml.safe_load((PROFILES / profile / "config.yaml").read_text()) or {}
            if not get(config, ("voice", "record_key")):
                drift.append("voice.record_key not set (push-to-talk)")
        if args.channel == "telegram" and (platforms.get(f"{profile}:telegram") or {}).get("state") != "connected":
            drift.append("telegram adapter not connected")
        if drift:
            problems.append(f"{profile}: " + "; ".join(drift))

    scope = f"{len(profiles)} profile(s) ({args.channel})"
    if problems:
        print(f"Voice runtime drift, {scope}:")
        for item in problems:
            print(f"- {item}")
        return 1
    print(f"Voice runtime matches 52_policies/telegram-audio-ptbr.md for {scope}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
