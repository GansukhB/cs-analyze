"""The Assistant's voice, through ElevenLabs: speech out and speech in.

Speech out is one call per paragraph: the chat streams a paragraph to the
browser as soon as Claude has finished it (see :mod:`app.services.assistant`),
and waiting for the whole reply before speaking any of it would throw that head
start away. Speech in is one call per spoken question, recorded in the browser
and relayed here so the key never leaves the server.

Ported from cstat's ``hltv/services/voice.py``, plus :func:`transcribe`. A
missing key or a failed call returns ``None`` rather than raising: audio is an
enhancement on top of the text, and a chat that loses its voice mid-conversation
should keep talking, just silently.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

import requests

from app.config import get_settings

logger = logging.getLogger(__name__)

_TTS_ENDPOINT = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
_STT_ENDPOINT = "https://api.elevenlabs.io/v1/speech-to-text"
# 64 kbps instead of the API default 128: each paragraph crosses the wire in one
# SSE frame before it can start speaking, and the difference doesn't matter on a
# chat voice.
_OUTPUT_FORMAT = "mp3_44100_64"


def is_configured() -> bool:
    settings = get_settings()
    return bool(settings.elevenlabs_api_key.get_secret_value() and settings.elevenlabs_voice_id)


def synthesize(text: str) -> bytes | None:
    """One paragraph of speech as MP3 bytes, or ``None`` if it could not be made."""
    text = (text or "").strip()
    if not text or not is_configured():
        return None
    settings = get_settings()
    try:
        response = requests.post(
            _TTS_ENDPOINT.format(voice_id=settings.elevenlabs_voice_id),
            params={"output_format": _OUTPUT_FORMAT},
            headers={
                "xi-api-key": settings.elevenlabs_api_key.get_secret_value(),
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
            json={
                "text": text,
                "model_id": settings.elevenlabs_model,
                "voice_settings": {"stability": 0.8, "similarity_boost": 0.95},
            },
            timeout=settings.elevenlabs_timeout,
        )
        response.raise_for_status()
        return response.content
    except requests.RequestException:
        logger.exception("ElevenLabs synthesis failed for %d chars of text", len(text))
        return None


# Over 100 keyterms ElevenLabs bills every clip as at least 20 seconds.
MAX_KEYTERMS = 100
_KEYTERM_BANNED = set("<>{}[]\\")


def _keyterm(term: str) -> str | None:
    term = "".join(ch for ch in term if ch not in _KEYTERM_BANNED).strip()
    return term if term and len(term) < 50 and len(term.split()) <= 5 else None


def transcribe(
    audio: bytes, filename: str, content_type: str, keyterms: Iterable[str] = ()
) -> str | None:
    """A spoken question as text, or ``None`` if it could not be read.

    The language is pinned (``elevenlabs_stt_language``): left to detect it, a
    short Mongolian question comes back as English or even Korean. ``keyterms``
    (team and map names, CS2 terms) keep the English words a Mongolian question
    is full of from being spelled out in Cyrillic ("Мираж" for Mirage).
    """
    if not audio or not is_configured():
        return None
    settings = get_settings()
    terms = list(dict.fromkeys(t for t in map(_keyterm, keyterms) if t))[:MAX_KEYTERMS]
    try:
        response = requests.post(
            _STT_ENDPOINT,
            headers={"xi-api-key": settings.elevenlabs_api_key.get_secret_value()},
            # A list of pairs: keyterms go as one repeated field each.
            data=[
                ("model_id", settings.elevenlabs_stt_model),
                ("language_code", settings.elevenlabs_stt_language),
                ("tag_audio_events", "false"),
                ("no_verbatim", "true"),
                *(("keyterms", t) for t in terms),
            ],
            files={"file": (filename or "question.webm", audio, content_type or "audio/webm")},
            timeout=settings.elevenlabs_timeout,
        )
        response.raise_for_status()
        return str(response.json().get("text") or "").strip()
    except (requests.RequestException, ValueError):
        logger.exception("ElevenLabs transcription failed for %d bytes of audio", len(audio))
        return None
