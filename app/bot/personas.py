"""Per-number AI personas, editable from the admin panel's Chatbot tab.

A persona is a full system prompt plus the WhatsApp numbers that get it
instead of the HotBoat sales bot (see webhook.py). Replaces dropping
"<digits>.txt" files in app/bot/custom_prompts/ — those files are imported
once into the DB on first use so they show up (and stay editable) in the UI.
"""
import logging
import os
import re
import time as _time
from typing import List, Optional

from app.db.connection import get_connection

logger = logging.getLogger(__name__)

_CUSTOM_PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "custom_prompts")
_IMPORT_MARKER_KEY = "personas_files_imported"

_tables_ready = False
_CACHE: dict = {}
_CACHE_TTL = 30


def digits_only(phone: str) -> str:
    return "".join(c for c in (phone or "") if c.isdigit())


def clear_cache() -> None:
    _CACHE.clear()


def ensure_tables() -> None:
    global _tables_ready
    if _tables_ready:
        return
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS bot_personas (
                    id            SERIAL PRIMARY KEY,
                    name          TEXT NOT NULL,
                    system_prompt TEXT NOT NULL,
                    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS bot_persona_numbers (
                    phone      TEXT PRIMARY KEY,
                    persona_id INT NOT NULL REFERENCES bot_personas(id) ON DELETE CASCADE
                )
            """)
            conn.commit()
    _tables_ready = True
    _import_prompt_files_once()


def _import_prompt_files_once() -> None:
    """One-time import of the legacy <digits>.txt files; files with identical
    content become one persona holding all their numbers."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT value FROM hotboat_settings WHERE key=%s", (_IMPORT_MARKER_KEY,))
                if cur.fetchone():
                    return
                by_content: dict = {}
                if os.path.isdir(_CUSTOM_PROMPTS_DIR):
                    for fname in sorted(os.listdir(_CUSTOM_PROMPTS_DIR)):
                        m = re.fullmatch(r"(\d+)\.txt", fname)
                        if not m:
                            continue
                        with open(os.path.join(_CUSTOM_PROMPTS_DIR, fname), "r", encoding="utf-8") as f:
                            content = f.read().strip()
                        if content:
                            by_content.setdefault(content, []).append(m.group(1))
                for content, phones in by_content.items():
                    name = content.splitlines()[0][:50].rstrip(" .,:;")
                    cur.execute(
                        "INSERT INTO bot_personas (name, system_prompt) VALUES (%s, %s) RETURNING id",
                        (name, content),
                    )
                    pid = cur.fetchone()[0]
                    for ph in phones:
                        cur.execute(
                            "INSERT INTO bot_persona_numbers (phone, persona_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                            (ph, pid),
                        )
                cur.execute(
                    "INSERT INTO hotboat_settings (key, value) VALUES (%s, 'true') "
                    "ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value",
                    (_IMPORT_MARKER_KEY,),
                )
                conn.commit()
    except Exception as e:
        logger.error(f"Persona file import failed: {e}")


def get_persona_prompt_for_number(phone: str) -> Optional[str]:
    d = digits_only(phone)
    if not d:
        return None
    hit = _CACHE.get(d)
    if hit and (_time.time() - hit[1]) < _CACHE_TTL:
        return hit[0]
    try:
        ensure_tables()
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT p.system_prompt FROM bot_persona_numbers n "
                    "JOIN bot_personas p ON p.id = n.persona_id WHERE n.phone = %s",
                    (d,),
                )
                row = cur.fetchone()
        prompt = (row[0] or "").strip() if row else None
        prompt = prompt or None
        _CACHE[d] = (prompt, _time.time())
        return prompt
    except Exception as e:
        logger.error(f"get_persona_prompt_for_number failed for {d}: {e}")
        return None


def list_personas() -> List[dict]:
    ensure_tables()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name, system_prompt FROM bot_personas ORDER BY id")
            personas = [{"id": r[0], "name": r[1], "system_prompt": r[2], "numbers": []} for r in cur.fetchall()]
            by_id = {p["id"]: p for p in personas}
            cur.execute("SELECT persona_id, phone FROM bot_persona_numbers ORDER BY phone")
            for pid, phone in cur.fetchall():
                if pid in by_id:
                    by_id[pid]["numbers"].append(phone)
    return personas


def _clean_numbers(numbers: List[str]) -> List[str]:
    out: List[str] = []
    for n in numbers or []:
        d = digits_only(n)
        if d and d not in out:
            out.append(d)
    return out


def save_persona(persona_id: Optional[int], name: str, system_prompt: str, numbers: List[str]) -> int:
    """Creates (persona_id None) or updates a persona and replaces its number
    list. Raises ValueError when a number already belongs to another persona."""
    ensure_tables()
    name = (name or "").strip()
    system_prompt = (system_prompt or "").strip()
    if not name:
        raise ValueError("El nombre es obligatorio")
    if not system_prompt:
        raise ValueError("El prompt es obligatorio")
    nums = _clean_numbers(numbers)
    with get_connection() as conn:
        with conn.cursor() as cur:
            if nums:
                cur.execute(
                    "SELECT n.phone, p.name FROM bot_persona_numbers n JOIN bot_personas p ON p.id=n.persona_id "
                    "WHERE n.phone = ANY(%s) AND n.persona_id IS DISTINCT FROM %s",
                    (nums, persona_id),
                )
                clash = cur.fetchall()
                if clash:
                    raise ValueError("; ".join(f"{ph} ya está en «{pn}»" for ph, pn in clash))
            if persona_id is None:
                cur.execute(
                    "INSERT INTO bot_personas (name, system_prompt) VALUES (%s, %s) RETURNING id",
                    (name, system_prompt),
                )
                persona_id = cur.fetchone()[0]
            else:
                cur.execute(
                    "UPDATE bot_personas SET name=%s, system_prompt=%s, updated_at=NOW() WHERE id=%s",
                    (name, system_prompt, persona_id),
                )
                if cur.rowcount == 0:
                    raise ValueError("Persona no encontrada")
                cur.execute("DELETE FROM bot_persona_numbers WHERE persona_id=%s", (persona_id,))
            for ph in nums:
                cur.execute("INSERT INTO bot_persona_numbers (phone, persona_id) VALUES (%s, %s)", (ph, persona_id))
            conn.commit()
    clear_cache()
    return persona_id


def delete_persona(persona_id: int) -> None:
    ensure_tables()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM bot_personas WHERE id=%s", (persona_id,))
            conn.commit()
    clear_cache()
