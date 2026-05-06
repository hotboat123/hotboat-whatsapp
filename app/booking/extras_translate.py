"""Translate extras catalog fields (ES → EN, PT) via Groq OpenAI-compatible API."""
import json
import logging
import re
from typing import Any, Dict

from openai import OpenAI

from app.config import get_settings

logger = logging.getLogger(__name__)


def translate_extra_fields(name_es: str, description_es: str) -> Dict[str, str]:
    """
    Return name_en, name_pt, description_en, description_pt.
    Source strings are Spanish (Chile tourism context).
    """
    settings = get_settings()
    if not (settings.groq_api_key or "").strip():
        raise RuntimeError("GROQ_API_KEY is not configured")

    name_es = (name_es or "").strip()
    description_es = (description_es or "").strip()
    if not name_es:
        raise ValueError("name is empty")

    client = OpenAI(
        api_key=settings.groq_api_key,
        base_url="https://api.groq.com/openai/v1",
    )
    model = "llama-3.3-70b-versatile"

    user = json.dumps(
        {"name_es": name_es, "description_es": description_es},
        ensure_ascii=False,
    )

    kwargs = dict(
        model=model,
        temperature=0.2,
        messages=[
            {
                "role": "system",
                "content": (
                    "You translate short tourism product lines from Spanish to English and "
                    "Brazilian Portuguese. Reply with a single JSON object only, no markdown, "
                    'keys: "name_en","name_pt","description_en","description_pt". '
                    "Keep proper nouns (HotBoat, Pucón, Chile) when appropriate. "
                    "If description_es is empty, return empty strings for both description fields."
                ),
            },
            {"role": "user", "content": user},
        ],
    )
    try:
        completion = client.chat.completions.create(
            **kwargs, response_format={"type": "json_object"}
        )
    except Exception as first_err:
        logger.warning("Groq json_object mode failed, retrying: %s", first_err)
        completion = client.chat.completions.create(**kwargs)
    try:
        raw = (completion.choices[0].message.content or "").strip()
    except Exception as e:
        logger.warning("Groq translate completion failed: %s", e)
        raise RuntimeError("Translation service unavailable") from e

    try:
        data: Dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", raw)
        if not m:
            raise ValueError("Model did not return JSON") from None
        data = json.loads(m.group(0))

    def _s(key: str) -> str:
        v = data.get(key)
        return (str(v) if v is not None else "").strip()

    return {
        "name_en": _s("name_en") or name_es,
        "name_pt": _s("name_pt") or name_es,
        "description_en": _s("description_en"),
        "description_pt": _s("description_pt"),
    }


def translate_catalog_i18n_fields(
    name_es: str,
    description_es: str,
    *,
    group_es: str = "",
) -> Dict[str, str]:
    """
    Translate experience / pack / lodging catalog lines (ES → EN, PT).

    Includes optional grouping label used for lodging. When ``group_es`` is empty,
    ``group_name_en`` and ``group_name_pt`` are returned as empty strings.
    """
    settings = get_settings()
    if not (settings.groq_api_key or "").strip():
        raise RuntimeError("GROQ_API_KEY is not configured")

    name_es = (name_es or "").strip()
    description_es = (description_es or "").strip()
    group_es_s = (group_es or "").strip()
    if not name_es:
        raise ValueError("name is empty")

    client = OpenAI(
        api_key=settings.groq_api_key,
        base_url="https://api.groq.com/openai/v1",
    )
    model = "llama-3.3-70b-versatile"

    user = json.dumps(
        {"name_es": name_es, "description_es": description_es, "group_es": group_es_s},
        ensure_ascii=False,
    )

    kwargs = dict(
        model=model,
        temperature=0.2,
        messages=[
            {
                "role": "system",
                "content": (
                    "You translate short tourism lodging, experience, and package catalog fields "
                    'from Spanish to English and Brazilian Portuguese. Reply with a single JSON object only, '
                    'no markdown, keys: '
                    '"name_en","name_pt","description_en","description_pt","group_name_en","group_name_pt". '
                    'If input group_es is empty, return empty strings for group_name_en and group_name_pt. '
                    'If description_es is empty, return empty strings for both description fields. '
                    "Keep proper nouns (HotBoat, Pucón, Chile) when appropriate."
                ),
            },
            {"role": "user", "content": user},
        ],
    )
    try:
        completion = client.chat.completions.create(
            **kwargs, response_format={"type": "json_object"}
        )
    except Exception as first_err:
        logger.warning("Groq json_object mode failed (catalog i18n), retrying: %s", first_err)
        completion = client.chat.completions.create(**kwargs)
    try:
        raw = (completion.choices[0].message.content or "").strip()
    except Exception as e:
        logger.warning("Groq translate completion failed (catalog i18n): %s", e)
        raise RuntimeError("Translation service unavailable") from e

    try:
        data: Dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", raw)
        if not m:
            raise ValueError("Model did not return JSON") from None
        data = json.loads(m.group(0))

    def _s(key: str) -> str:
        v = data.get(key)
        return (str(v) if v is not None else "").strip()

    if not group_es_s:
        gin, gpt = "", ""
    else:
        gin = _s("group_name_en") or group_es_s
        gpt = _s("group_name_pt") or group_es_s

    return {
        "name_en": _s("name_en") or name_es,
        "name_pt": _s("name_pt") or name_es,
        "description_en": _s("description_en"),
        "description_pt": _s("description_pt"),
        "group_name_en": gin,
        "group_name_pt": gpt,
    }
