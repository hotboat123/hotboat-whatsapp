"""Speech-to-text for incoming WhatsApp voice notes.

Lets Popeye actually understand what a customer said in an audio message
(and reply to it through the normal bot pipeline) instead of only
acknowledging "recibimos tu audio". Uses Groq's hosted Whisper endpoint —
same GROQ_API_KEY already configured for chat completions, see
app/bot/ai_handler.py's _PROVIDER_ENDPOINTS.

Language is intentionally left to auto-detect rather than forced to "es":
Whisper then transcribes in whatever language was spoken, and the existing
free-text language detection / multi-language replies already used for
typed messages (ConversationManager._infer_language_from_free_text) take it
from there — so a tourist's audio in English or Portuguese is also handled,
without a separate translation step.
"""
import asyncio
import logging
from typing import Optional

from openai import OpenAI

from app.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

# Groq-hosted Whisper model — fast and inexpensive, well within WhatsApp
# voice-note length/size. See https://console.groq.com/docs/speech-to-text
_TRANSCRIBE_MODEL = "whisper-large-v3-turbo"

_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=settings.groq_api_key, base_url="https://api.groq.com/openai/v1")
    return _client


def _transcribe_sync(file_path: str) -> Optional[str]:
    with open(file_path, "rb") as f:
        # verbose_json (vs. the default "json") also returns .duration —
        # Whisper is billed by audio length, not tokens, so that's the
        # usage figure worth tracking here (see app/bot/ai_usage.py).
        result = _get_client().audio.transcriptions.create(
            model=_TRANSCRIBE_MODEL,
            file=f,
            response_format="verbose_json",
        )
    try:
        from app.bot.ai_usage import log_usage
        log_usage(
            provider="groq",
            model=_TRANSCRIBE_MODEL,
            call_type="transcription",
            audio_seconds=getattr(result, "duration", None),
        )
    except Exception as e:
        logger.warning(f"Audio transcription usage logging skipped: {e}")
    text = (result.text or "").strip()
    return text or None


async def transcribe_audio(file_path: str) -> Optional[str]:
    """Transcribe a local audio file to text. Returns None (never raises) on
    any failure — e.g. no/garbled speech, oversized file, API outage — so
    callers can fall back to the old "acknowledge, don't understand"
    behavior instead of breaking the bot. Runs the (synchronous) SDK call in
    a thread so it doesn't block the event loop other requests share."""
    try:
        return await asyncio.to_thread(_transcribe_sync, file_path)
    except Exception as e:
        logger.warning(f"Audio transcription failed for {file_path}: {e}")
        return None
