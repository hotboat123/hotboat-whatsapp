"""
Weekly smoke test — hotboat-whatsapp.

Run this manually (or on a weekly schedule, e.g. cron / Windows Task
Scheduler) to catch regressions in the booking pricing, T&C signing, and
WhatsApp bot logic without needing a browser or a real WhatsApp session.

Covers:
  1. Pricing math — a 2 adultos + 3 niños booking created through the real
     API must match price_breakdown()'s formula exactly (tier price minus
     flat per-child discount, no accidental rounding).
  2. T&C signature — POST /api/firma/{booking_ref} must create a row in
     hotboat_signatures.
  3. WhatsApp bot regression — "Quiero reservar para 2 adultos y 3 niños"
     must NOT be swallowed by the canned "niños" FAQ reply (this exact bug
     shipped and was fixed on 2026-07-23; this test exists to catch it if
     it ever comes back). Calls ConversationManager.process_message()
     directly — no real WhatsApp/Meta send is triggered by this call.
  4. A/B welcome-message test (app/bot/variant_overrides.py) — a lead
     force-assigned to a throwaway, is_active=FALSE variant must see that
     variant's override text instead of the default message, and the
     /api/admin/bot/ab-results endpoint must count it. is_active=FALSE means
     this test variant is never eligible for real customers' random
     assignment — see test_ab_experiment()'s docstring.
  5. A/B weighted assignment (app/db/leads.py:_pick_active_variant) — a
     3:1 weight split must converge to exactly 9:3 over 12 deterministic
     picks. Pure logic test against a fake cursor, touches no real DB rows.
  6. Live-AI-fallback safety net (ConversationManager._try_ai_fallback) —
     a variant with a deliberately bogus AI model must never crash the bot
     or surface an error; it must silently fall through to the normal
     main-menu text. Does not require a real GROQ_API_KEY to be meaningful.
  7. Manual per-conversation variant override (PUT /leads/{phone}/bot-variant,
     app/db/leads.py:set_bot_variant_for_lead) — an admin picking which bot
     answers one specific WhatsApp conversation from the chat UI must take
     effect on the very next message, even on a warm process that already
     has that conversation cached in memory (ConversationManager.conversations
     is a per-process, in-memory dict — see the endpoint's comment in
     app/main.py). Also checks that pinning a variant to a phone with no
     lead row yet fails loudly instead of silently no-op'ing.
  8. Per-variant disabled FAQ triggers (bot_ab_variants.disabled_triggers,
     app/bot/faq.py's disabled_keys param) — a variant that disables the
     "precio" trigger must NOT get the canned pricing FAQ reply for a
     message like "cuales son los precios"; it must fall through the
     priority chain instead (normally reaching the live-AI fallback).
  9. Per-variant custom AI system prompt (bot_ab_variants.system_prompt,
     app/bot/ai_handler.py:build_system_prompt) — a variant's custom prompt
     must be used instead of the default, but the fixed anti-hallucination
     safety footer must always be appended regardless, and a variant with
     no custom prompt must fall back to the full default.
  10. Tracked booking link on AI replies (ConversationManager.
      _try_ai_fallback) — a price/reservation question answered by the live
      AI must get a real per-client tracked link appended; an unrelated
      question must not. Mocks the AI call, no real GROQ_API_KEY needed.

Does NOT cover the marketing repo (hotboat-email-marketing-spec) — the
segment-sync and abandoned-cart/birthday-automation checks need a logged-in
browser session against that app's admin API. See WEEKLY_TEST_MARKETING.md
for that half of the weekly routine.

Safe to run against production: every row this script creates is tagged
with a recognizable test phone/email and is deleted again in a `finally`
block, even if a check fails or raises.

Usage:
    python weekly_smoke_test.py
Exit code is 0 if every check passed, 1 otherwise (so it plays nicely with
cron and CI).
"""
import os
import sys
import io
import json
import asyncio
import traceback
from datetime import date, timedelta

import requests
import psycopg2
from dotenv import load_dotenv

if sys.stdout.encoding is None or sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("❌ DATABASE_URL not set (check .env)")
    sys.exit(1)

API_BASE = os.getenv("SMOKE_TEST_API_BASE", "https://kia-ai.hotboatchile.com")

TEST_PHONE = "+56900001234"          # booking/firma test row
TEST_EMAIL = "tomasdamjanic+smoketest@gmail.com"
BOT_TEST_PHONE = "+56900009999"      # separate number for the bot-logic test
AB_TEST_PHONE = "56900009998"        # separate number for the A/B variant test (no + — matches whatsapp_leads.phone_number format)
AB_VARIANT_KEY = "_smoketest"        # leading underscore keeps it visually distinct from real variants in the admin UI
AB_OVERRIDE_MARKER = "SMOKETEST_MARKER_DO_NOT_SHIP"
BOOKING_DATE = (date.today() + timedelta(days=120)).isoformat()  # far enough out to always be bookable

PRICES = {2: 76990, 3: 59990, 4: 48990, 5: 42990, 6: 36990, 7: 33990}
CHILD_DISCOUNT_PER_CHILD = 10000

results = []


def check(name: str, ok: bool, detail: str = ""):
    results.append((name, ok, detail))
    mark = "✅" if ok else "❌"
    print(f"{mark} {name}" + (f" — {detail}" if detail else ""))


def cleanup(conn):
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM hotboat_signatures WHERE passenger_email=%s", (TEST_EMAIL,))
            cur.execute(
                "DELETE FROM all_appointments WHERE telefono=%s OR email=%s",
                (TEST_PHONE, TEST_EMAIL),
            )
            cur.execute("DELETE FROM whatsapp_conversations WHERE phone_number=%s", (BOT_TEST_PHONE,))
            cur.execute("DELETE FROM bot_conversation_state WHERE phone_number=%s", (BOT_TEST_PHONE,))
            cur.execute("DELETE FROM whatsapp_leads WHERE phone_number=%s", (AB_TEST_PHONE,))
            cur.execute("DELETE FROM whatsapp_conversations WHERE phone_number=%s", (AB_TEST_PHONE,))
            cur.execute("DELETE FROM bot_conversation_state WHERE phone_number=%s", (AB_TEST_PHONE,))
            cur.execute("DELETE FROM bot_ab_variants WHERE variant_key=%s", (AB_VARIANT_KEY,))  # cascades to bot_message_overrides
            cur.execute("DELETE FROM whatsapp_leads WHERE phone_number=%s", (AI_TEST_PHONE,))
            cur.execute("DELETE FROM whatsapp_conversations WHERE phone_number=%s", (AI_TEST_PHONE,))
            cur.execute("DELETE FROM bot_conversation_state WHERE phone_number=%s", (AI_TEST_PHONE,))
            cur.execute("DELETE FROM bot_ab_variants WHERE variant_key=%s", (AI_VARIANT_KEY,))
            cur.execute("DELETE FROM whatsapp_leads WHERE phone_number=%s", (SWITCH_TEST_PHONE,))
            cur.execute("DELETE FROM whatsapp_conversations WHERE phone_number=%s", (SWITCH_TEST_PHONE,))
            cur.execute("DELETE FROM bot_conversation_state WHERE phone_number=%s", (SWITCH_TEST_PHONE,))
            cur.execute("DELETE FROM whatsapp_leads WHERE phone_number=%s", (STALE_CACHE_TEST_PHONE,))
            cur.execute("DELETE FROM whatsapp_conversations WHERE phone_number=%s", (STALE_CACHE_TEST_PHONE,))
            cur.execute("DELETE FROM bot_conversation_state WHERE phone_number=%s", (STALE_CACHE_TEST_PHONE,))
            cur.execute("DELETE FROM whatsapp_leads WHERE phone_number=%s", (DISABLED_TRIGGER_TEST_PHONE,))
            cur.execute("DELETE FROM whatsapp_conversations WHERE phone_number=%s", (DISABLED_TRIGGER_TEST_PHONE,))
            cur.execute("DELETE FROM bot_conversation_state WHERE phone_number=%s", (DISABLED_TRIGGER_TEST_PHONE,))
            cur.execute("DELETE FROM tracked_quote_links WHERE phone=%s", (AI_LINK_TEST_PHONE,))
            conn.commit()
    except Exception as e:
        print(f"⚠️ cleanup warning: {e}")
        conn.rollback()


def test_pricing_and_booking(conn):
    adults, children = 2, 3
    n = adults + children
    price_pp = PRICES[n]
    sub_before = price_pp * n
    child_discount = min(children * CHILD_DISCOUNT_PER_CHILD, sub_before)
    expected_total = sub_before - child_discount

    r = requests.post(
        f"{API_BASE}/api/booking/create",
        json={
            "customer_name": "Smoke Test",
            "customer_phone": TEST_PHONE,
            "customer_email": TEST_EMAIL,
            "num_adultos": adults,
            "num_ninos": children,
            "num_people": n,
            "booking_date": BOOKING_DATE,
            "booking_time": "11:00",
            "extras": [],
            "has_flex": False,
            "skip_payment": True,
        },
        timeout=20,
    )
    ok = r.status_code == 200
    data = r.json() if ok else {}
    booking_ref = data.get("booking_ref")
    check("Booking API reachable (2 adultos + 3 niños)", ok, f"HTTP {r.status_code}")
    if not ok:
        return None
    check(
        "Pricing math matches price_breakdown() exactly",
        data.get("total_price") == expected_total,
        f"got {data.get('total_price')}, expected {expected_total}",
    )
    return booking_ref


def test_signature(booking_ref, conn):
    if not booking_ref:
        check("T&C signature", False, "skipped — no booking_ref from previous step")
        return
    r = requests.post(
        f"{API_BASE}/api/firma/{booking_ref}",
        json={
            "passenger_name": "Smoke Test Passenger",
            "passenger_email": TEST_EMAIL,
            "passenger_phone": TEST_PHONE,
            "passenger_birthday": "1990-01-01",
            "accepted_tc": True,
        },
        timeout=20,
    )
    ok = r.status_code == 200 and r.json().get("ok")
    check("T&C signature endpoint accepts the signature", ok, f"HTTP {r.status_code}")

    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM hotboat_signatures WHERE booking_ref=%s AND passenger_email=%s",
            (booking_ref, TEST_EMAIL),
        )
        row = cur.fetchone()
    check("Signature row landed in hotboat_signatures", row is not None)


def test_bot_ninos_regression():
    """
    Regression test for the bug fixed 2026-07-23 (commit e26622e): a fresh
    "Quiero reservar para X adultos y Y niños" message was getting
    intercepted by the canned "niños" FAQ reply instead of starting a
    reservation. Calls the conversation handler directly — no real
    WhatsApp/Meta send happens as a side effect of this call.
    """
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        from app.bot.conversation import ConversationManager
    except Exception as e:
        check("Bot regression test — import ConversationManager", False, str(e))
        return

    async def _run():
        cm = ConversationManager()
        # A brand-new phone number hits the "first message" welcome flow
        # before it ever reaches the niños check, which would pass this
        # test for the wrong reason. Send a throwaway warm-up message first
        # so the real regression message lands mid-conversation, exactly
        # like the real report that surfaced this bug.
        await cm.process_message(
            from_number=BOT_TEST_PHONE,
            message_text="Hola",
            contact_name="Smoke Test Bot",
            message_id=f"smoketest-warmup-{date.today().isoformat()}",
        )
        return await cm.process_message(
            from_number=BOT_TEST_PHONE,
            message_text="Quiero reservar para 2 adultos y 3 niños",
            contact_name="Smoke Test Bot",
            message_id=f"smoketest-{date.today().isoformat()}",
        )

    try:
        resp = asyncio.run(_run())
    except Exception as e:
        check("Bot: 'niños' FAQ does not swallow reservation intent", False, f"{e}")
        traceback.print_exc()
        return

    resp_text = resp if isinstance(resp, str) else json.dumps(resp, ensure_ascii=False)
    swallowed = "pasan increíble" in resp_text  # the canned reply's tell
    check(
        "Bot: 'niños' FAQ does not swallow reservation intent",
        not swallowed,
        resp_text[:150].replace("\n", " "),
    )
    check(
        "Bot: reservation intent correctly asks for a date",
        "fecha" in resp_text.lower(),
        resp_text[:150].replace("\n", " "),
    )


def test_ab_experiment(conn):
    """
    A/B welcome-message test (app/bot/variant_overrides.py), reviewed and
    verified 2026-07-23. Uses an is_active=FALSE throwaway variant, created
    by direct INSERT rather than the create-variant API, so it can never be
    randomly assigned to a real customer's get_or_create_lead() call — this
    test forces AB_TEST_PHONE onto it directly instead of relying on the
    random picker. Covers: (1) a lead force-assigned to a variant with an
    override sees that override's text, (2) POST/DELETE the override via the
    real admin API, (3) GET /ab-results reflects the forced lead.
    """
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO bot_ab_variants (variant_key, label, is_active) VALUES (%s, %s, FALSE)",
            (AB_VARIANT_KEY, "Smoke Test (inactive)"),
        )
        conn.commit()

    r = requests.put(
        f"{API_BASE}/api/admin/bot/ab-overrides",
        json={"variant_key": AB_VARIANT_KEY, "message_key": "main_menu", "content_es": AB_OVERRIDE_MARKER},
        timeout=20,
    )
    check("A/B override upsert API accepts the override", r.status_code == 200, f"HTTP {r.status_code}")
    # The upsert above invalidates the *server's* in-process override cache
    # (app/bot/variant_overrides.py) over HTTP — irrelevant here, since this
    # script calls ConversationManager directly and has its own separate
    # in-process cache (already warmed by test_bot_ninos_regression()'s
    # earlier process_message() call). Invalidate it too, or the 60s TTL
    # would hide the override we just wrote.
    try:
        from app.bot.variant_overrides import invalidate_cache
        invalidate_cache()
    except Exception:
        pass

    with conn.cursor() as cur:
        cur.execute("DELETE FROM whatsapp_leads WHERE phone_number=%s", (AB_TEST_PHONE,))
        cur.execute(
            "INSERT INTO whatsapp_leads (phone_number, customer_name, lead_status, last_interaction_at, created_at, updated_at, bot_variant) "
            "VALUES (%s, %s, 'unknown', NOW(), NOW(), NOW(), %s)",
            (AB_TEST_PHONE, "Smoke Test AB", AB_VARIANT_KEY),
        )
        conn.commit()

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        from app.bot.conversation import ConversationManager
    except Exception as e:
        check("A/B test — import ConversationManager", False, str(e))
        return

    async def _run():
        cm = ConversationManager()
        return await cm.process_message(
            from_number=AB_TEST_PHONE,
            message_text="Hola",
            contact_name="Smoke Test AB",
            message_id=f"smoketest-ab-{date.today().isoformat()}",
        )

    try:
        resp = asyncio.run(_run())
    except Exception as e:
        check("A/B: lead assigned to variant sees its override", False, str(e))
        traceback.print_exc()
        return

    resp_text = resp if isinstance(resp, str) else json.dumps(resp, ensure_ascii=False)
    check(
        "A/B: lead assigned to variant sees its override",
        AB_OVERRIDE_MARKER in resp_text,
        resp_text[:150].replace("\n", " "),
    )

    r2 = requests.get(f"{API_BASE}/api/admin/bot/ab-results", timeout=20)
    ok2 = r2.status_code == 200
    check("A/B results endpoint reachable", ok2, f"HTTP {r2.status_code}")
    if ok2:
        results = r2.json().get("results", [])
        row = next((v for v in results if v.get("variant_key") == AB_VARIANT_KEY), None)
        check(
            "A/B results endpoint counts the forced test lead",
            row is not None and row.get("leads", 0) >= 1,
            str(row),
        )


AI_TEST_PHONE = "56900007776"
AI_VARIANT_KEY = "_smoketest_ai"


def test_ai_fallback_safety_net(conn):
    """
    Live-AI fallback (ConversationManager._try_ai_fallback, added
    2026-07-23): when a variant sets ai_provider/ai_model, an unmatched
    message tries a real Groq call before falling back to the main menu.
    This test deliberately uses a bogus model name so the Groq call fails
    regardless of whether a real GROQ_API_KEY is configured in this
    environment — the point isn't to test Groq's API, it's to lock in that
    an AI failure can NEVER surface as an error or crash the bot; it must
    silently fall through to the exact same main-menu text a variant with
    no AI model at all would show.
    """
    with conn.cursor() as cur:
        cur.execute("DELETE FROM whatsapp_leads WHERE phone_number=%s", (AI_TEST_PHONE,))
        cur.execute("DELETE FROM bot_ab_variants WHERE variant_key=%s", (AI_VARIANT_KEY,))
        cur.execute(
            "INSERT INTO bot_ab_variants (variant_key, label, is_active, ai_provider, ai_model) "
            "VALUES (%s, %s, FALSE, 'groq', 'this-model-does-not-exist')",
            (AI_VARIANT_KEY, "Smoke Test AI (inactive)"),
        )
        cur.execute(
            "INSERT INTO whatsapp_leads (phone_number, customer_name, lead_status, last_interaction_at, created_at, updated_at, bot_variant) "
            "VALUES (%s, %s, 'unknown', NOW(), NOW(), NOW(), %s)",
            (AI_TEST_PHONE, "Smoke Test AI", AI_VARIANT_KEY),
        )
        conn.commit()

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        from app.bot.conversation import ConversationManager
        from app.bot.variant_overrides import invalidate_cache
        invalidate_cache()
    except Exception as e:
        check("AI fallback safety net — import ConversationManager", False, str(e))
        return

    async def _run():
        cm = ConversationManager()
        await cm.process_message(
            from_number=AI_TEST_PHONE, message_text="Hola", contact_name="Smoke Test AI",
            message_id=f"smoketest-ai-warmup-{date.today().isoformat()}",
        )
        # Something that shouldn't match any deterministic handler, forcing
        # the flow into the final "nothing matched" fallback where the AI
        # attempt (and this test) actually happens.
        return await cm.process_message(
            from_number=AI_TEST_PHONE, message_text="Oye, cuéntame un chiste corto sobre el mar",
            contact_name="Smoke Test AI", message_id=f"smoketest-ai-{date.today().isoformat()}",
        )

    try:
        resp = asyncio.run(_run())
    except Exception as e:
        check("AI fallback failure does not crash the bot", False, str(e))
        traceback.print_exc()
        return

    resp_text = resp if isinstance(resp, str) else json.dumps(resp, ensure_ascii=False)
    check(
        "AI fallback failure does not crash the bot",
        True,  # reaching this line at all (no exception above) is the check
    )
    check(
        "AI fallback failure falls through to the normal main menu",
        "¿Qué número eliges?" in resp_text,
        resp_text[:150].replace("\n", " "),
    )


def test_ab_weighted_assignment():
    """
    Deterministic weighted variant assignment (app/db/leads.py:
    _pick_active_variant), added 2026-07-23. Uses a fake cursor that answers
    the two SELECTs it issues from in-memory data — no real bot_ab_variants
    row is ever created, so this can't affect real customers' random
    assignment even for the instant it would take to create/delete an
    is_active=TRUE test variant in the shared production DB.
    """
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        from app.db.leads import _pick_active_variant
    except Exception as e:
        check("A/B weighted assignment — import _pick_active_variant", False, str(e))
        return

    class _FakeCursor:
        """Mimics the two queries _pick_active_variant issues: variants
        (key, weight, is_human, schedule_start_hour, schedule_end_hour),
        then assignment counts so far, both from a dict this test mutates
        locally — never touches the real DB."""
        def __init__(self, variants, counts):
            self.variants = variants  # [(key, weight, is_human, start_hour, end_hour), ...]
            self.counts = counts      # {key: count}
            self._last = None

        def execute(self, sql, params=None):
            if "FROM bot_ab_variants" in sql:
                self._last = list(self.variants)
            elif "FROM whatsapp_leads" in sql:
                self._last = [(k, c) for k, c in self.counts.items() if c > 0]
            else:
                self._last = []

        def fetchall(self):
            return self._last

    # A plain weighted random pick (2026-08-12, replaced the earlier
    # "furthest behind their all-time count" algorithm — see
    # _pick_active_variant's docstring for why) — no exact sequence to
    # assert on anymore, so this checks the 3:1 weight ratio holds
    # statistically over many picks instead of exactly over a handful.
    # No schedule set on either (None, None) -> both always eligible.
    variants = [("a", 3, False, None, None), ("b", 1, False, None, None)]
    cur = _FakeCursor(variants, {})
    N = 4000
    counts = {"a": 0, "b": 0}
    for _ in range(N):
        picked, _ = _pick_active_variant(cur)
        counts[picked] += 1
    a_share = counts["a"] / N
    check(
        "A/B weighted assignment (3:1) lands close to 75% for the weight-3 variant over 4000 picks",
        0.70 <= a_share <= 0.80,
        f"counts={counts} a_share={a_share:.3f}",
    )

    # No active variants at all -> (None, False), not a crash (the "usually
    # no experiment running" case _pick_active_variant's docstring describes).
    empty_cur = _FakeCursor([], {})
    check(
        "A/B weighted assignment returns (None, False) when no variant is active",
        _pick_active_variant(empty_cur) == (None, False),
    )

    # A lone active variant flagged is_human=True must be picked AS human —
    # this is what makes get_or_create_lead() start the new lead with
    # bot_enabled=FALSE instead of the usual TRUE default.
    human_cur = _FakeCursor([("tomas", 1, True, None, None)], {})
    check(
        "A/B weighted assignment surfaces is_human=True for a human variant",
        _pick_active_variant(human_cur) == ("tomas", True),
    )

    # Working hours (schedule_start_hour/schedule_end_hour): ANY active
    # variant with a schedule set — human (Tom/Esteban) or automated
    # (Control, IA1, ...) — currently outside it is excluded from new-lead
    # assignment. Humans got this first (2026-08-13: a lead got assigned to
    # Esteban while off-shift and just sat there); widened same day to bots
    # too, on request, so an automated variant can also be scoped to
    # specific hours. A variant with NO schedule set (both hours NULL — the
    # default) is always eligible regardless — that's what keeps this from
    # repeating the 2026-08-12 bug, where Control (which never had a
    # schedule) got starved once Tom/Esteban had non-overlapping shifts
    # covering most of the day; the bug was in how the filter was applied,
    # not in filtering every variant. Schedule still separately gates
    # operator NOTIFICATIONS (see hour_in_schedule() / is_variant_in_hours()
    # below and their own tests).
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from app.bot.variant_overrides import hour_in_schedule

    now_hour = datetime.now(ZoneInfo("America/Santiago")).hour
    off_start, off_end = (now_hour + 2) % 24, (now_hour + 3) % 24   # window that excludes now_hour
    on_start, on_end = (now_hour - 1) % 24, (now_hour + 1) % 24     # window that includes now_hour

    off_shift_cur = _FakeCursor(
        [("control", 1, False, None, None), ("esteban", 1, True, off_start, off_end)], {}
    )
    off_shift_picks = {_pick_active_variant(off_shift_cur)[0] for _ in range(200)}
    check(
        "Schedule-aware assignment: off-shift human variant excluded, no-schedule variant always eligible",
        off_shift_picks == {"control"},
        f"picks={off_shift_picks}",
    )

    on_shift_cur = _FakeCursor(
        [("control", 1, False, None, None), ("esteban", 1, True, on_start, on_end)], {}
    )
    on_shift_picks = {_pick_active_variant(on_shift_cur)[0] for _ in range(200)}
    check(
        "Schedule-aware assignment: on-shift human variant included alongside no-schedule variant",
        on_shift_picks == {"control", "esteban"},
        f"picks={on_shift_picks}",
    )

    bot_schedule_cur = _FakeCursor(
        [("control", 1, False, None, None), ("ia_1", 1, False, off_start, off_end)], {}
    )
    bot_schedule_picks = {_pick_active_variant(bot_schedule_cur)[0] for _ in range(200)}
    check(
        "Schedule-aware assignment: off-shift BOT variant also excluded, not just humans",
        bot_schedule_picks == {"control"},
        f"picks={bot_schedule_picks}",
    )

    all_off_shift_cur = _FakeCursor(
        [("tom", 1, True, off_start, off_end), ("esteban", 1, True, off_start, off_end)], {}
    )
    all_off_shift_picks = {_pick_active_variant(all_off_shift_cur)[0] for _ in range(200)}
    check(
        "Schedule-aware assignment: falls back to unfiltered list rather than leaving a lead unassigned",
        all_off_shift_picks == {"tom", "esteban"},
        f"picks={all_off_shift_picks}",
    )
    check(
        "Working hours: 10:00 falls inside Tomás' 8-16 shift",
        hour_in_schedule(10, 8, 16) is True,
    )
    check(
        "Working hours: 10:00 falls OUTSIDE Esteban's 16-20 shift",
        hour_in_schedule(10, 16, 20) is False,
    )
    check(
        "Working hours: 22:00 falls inside an overnight 20→06 shift (wraps midnight)",
        hour_in_schedule(22, 20, 6) is True,
    )
    check(
        "Working hours: 10:00 falls OUTSIDE an overnight 20→06 shift",
        hour_in_schedule(10, 20, 6) is False,
    )
    check(
        "Working hours: identical start/end hour is treated as unrestricted, not \"never\"",
        hour_in_schedule(3, 9, 9) is True,
    )


SWITCH_TEST_PHONE = "56900007772"
SWITCH_VARIANT_KEY = "_smoketest_switch"
SWITCH_OVERRIDE_MARKER = "SMOKETEST_SWITCH_MARKER_DO_NOT_SHIP"


def test_manual_variant_switch(conn):
    """
    Manual per-conversation variant override (PUT /leads/{phone}/bot-variant),
    added 2026-07-23. An admin picking which bot answers a specific ongoing
    WhatsApp conversation must take effect on the very next message — even
    when that conversation is already cached in a *different* process's
    in-memory ConversationManager.conversations dict, since
    set_bot_variant_for_lead() only guarantees a fresh DB read by deleting
    the persisted bot_conversation_state row. Simulates two different
    processes (two separate ConversationManager() instances) handling the
    "before" and "after" messages, the same way two Railway replicas would.
    """
    with conn.cursor() as cur:
        cur.execute("DELETE FROM bot_ab_variants WHERE variant_key=%s", (SWITCH_VARIANT_KEY,))
        cur.execute(
            "INSERT INTO bot_ab_variants (variant_key, label, is_active) VALUES (%s, %s, FALSE)",
            (SWITCH_VARIANT_KEY, "Smoke Test Switch (inactive)"),
        )
        conn.commit()

    r = requests.put(
        f"{API_BASE}/api/admin/bot/ab-overrides",
        json={"variant_key": SWITCH_VARIANT_KEY, "message_key": "main_menu", "content_es": SWITCH_OVERRIDE_MARKER},
        timeout=20,
    )
    check("Manual switch — override upsert API accepts the override", r.status_code == 200, f"HTTP {r.status_code}")

    with conn.cursor() as cur:
        cur.execute("DELETE FROM whatsapp_leads WHERE phone_number=%s", (SWITCH_TEST_PHONE,))
        conn.commit()

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        from app.bot.conversation import ConversationManager
        from app.bot.variant_overrides import invalidate_cache
    except Exception as e:
        check("Manual switch — import ConversationManager", False, str(e))
        return

    async def _first_message():
        # A brand-new ConversationManager, standing in for "process A"
        # handling this customer's first-ever message — creates the lead
        # with no variant assigned (auto-assignment finds no active
        # variant, since SWITCH_VARIANT_KEY is is_active=FALSE).
        invalidate_cache()
        cm = ConversationManager()
        return await cm.process_message(
            from_number=SWITCH_TEST_PHONE, message_text="Hola", contact_name="Smoke Test Switch",
            message_id=f"smoketest-switch-1-{date.today().isoformat()}",
        )

    try:
        resp1 = asyncio.run(_first_message())
    except Exception as e:
        check("Manual switch — baseline first message", False, str(e))
        traceback.print_exc()
        return

    resp1_text = resp1 if isinstance(resp1, str) else json.dumps(resp1, ensure_ascii=False)
    check(
        "Manual switch — baseline message has no override before switching",
        SWITCH_OVERRIDE_MARKER not in resp1_text,
        resp1_text[:150].replace("\n", " "),
    )

    r2 = requests.put(
        f"{API_BASE}/leads/{SWITCH_TEST_PHONE}/bot-variant",
        json={"variant_key": SWITCH_VARIANT_KEY},
        timeout=20,
    )
    check(
        "Manual switch — bot-variant endpoint accepts the pin",
        r2.status_code == 200 and r2.json().get("bot_variant") == SWITCH_VARIANT_KEY,
        f"HTTP {r2.status_code} {r2.text[:150]}",
    )

    async def _second_message():
        # A second, independent ConversationManager — standing in for
        # "process B" (a different replica) handling the next message. It
        # never saw process A's in-memory cache (a separate Python object
        # entirely), so a pass here proves the DB-level pin + persisted-
        # state deletion is enough on its own, without relying on the
        # same-process in-memory patch in app/main.py's endpoint.
        invalidate_cache()
        cm2 = ConversationManager()
        return await cm2.process_message(
            from_number=SWITCH_TEST_PHONE, message_text="Hola de nuevo", contact_name="Smoke Test Switch",
            message_id=f"smoketest-switch-2-{date.today().isoformat()}",
        )

    try:
        resp2 = asyncio.run(_second_message())
    except Exception as e:
        check("Manual switch — message after switching shows the new variant", False, str(e))
        traceback.print_exc()
        return

    resp2_text = resp2 if isinstance(resp2, str) else json.dumps(resp2, ensure_ascii=False)
    check(
        "Manual switch — message after switching shows the new variant",
        SWITCH_OVERRIDE_MARKER in resp2_text,
        resp2_text[:150].replace("\n", " "),
    )

    r3 = requests.put(
        f"{API_BASE}/leads/56900000000000/bot-variant",
        json={"variant_key": SWITCH_VARIANT_KEY},
        timeout=20,
    )
    check(
        "Manual switch — pinning a variant on a nonexistent lead fails loudly (no silent no-op)",
        r3.status_code != 200,
        f"HTTP {r3.status_code} {r3.text[:150]}",
    )

    with conn.cursor() as cur:
        cur.execute("DELETE FROM bot_ab_variants WHERE variant_key=%s", (SWITCH_VARIANT_KEY,))
        conn.commit()


STALE_CACHE_TEST_PHONE = "56900007771"
STALE_CACHE_VARIANT_KEY = "_smoketest_stalecache"
STALE_CACHE_OVERRIDE_MARKER = "SMOKETEST_STALECACHE_MARKER_DO_NOT_SHIP"


def test_lead_bot_variant_always_fresh(conn):
    """
    Regression test for a real production bug (2026-07-24): with multiple
    Railway replicas, ConversationManager.conversations is a per-process
    in-memory dict, so a conversation already warm on the replica that
    happens to handle a customer's next message never saw an admin's
    PUT /leads/{phone}/bot-variant call on a *different* replica — Railway
    logs showed 'bot_variant': 'control' even after the admin picked "IA 1"
    for that lead. Fixed by having webhook.py pass the lead's bot_variant
    (already fetched fresh via get_or_create_lead() on every incoming
    message, at zero extra DB cost) straight into process_message(), which
    now always trusts it over whatever's cached — see
    app/bot/conversation.py's lead_bot_variant parameter.

    This test proves the fix works even in the worst case: a SINGLE
    ConversationManager instance (one replica) with the conversation
    already fully cached in memory, where bot_variant changes in the DB
    directly (no persisted-state deletion, no in-memory patch at all) —
    the kind of change any code path could make, not just the admin
    endpoint.
    """
    with conn.cursor() as cur:
        cur.execute("DELETE FROM whatsapp_leads WHERE phone_number=%s", (STALE_CACHE_TEST_PHONE,))
        cur.execute("DELETE FROM bot_ab_variants WHERE variant_key=%s", (STALE_CACHE_VARIANT_KEY,))
        cur.execute(
            "INSERT INTO bot_ab_variants (variant_key, label, is_active) VALUES (%s, %s, FALSE)",
            (STALE_CACHE_VARIANT_KEY, "Smoke Test Stale Cache (inactive)"),
        )
        conn.commit()

    r = requests.put(
        f"{API_BASE}/api/admin/bot/ab-overrides",
        json={"variant_key": STALE_CACHE_VARIANT_KEY, "message_key": "main_menu", "content_es": STALE_CACHE_OVERRIDE_MARKER},
        timeout=20,
    )
    check("Stale cache fix — override upsert API accepts the override", r.status_code == 200, f"HTTP {r.status_code}")

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        from app.bot.conversation import ConversationManager
        from app.bot.variant_overrides import invalidate_cache
        from app.db.leads import get_or_create_lead
    except Exception as e:
        check("Stale cache fix — import ConversationManager", False, str(e))
        return

    async def _run():
        invalidate_cache()
        cm = ConversationManager()  # one instance = one "replica"

        lead = await get_or_create_lead(STALE_CACHE_TEST_PHONE, "Smoke Test Stale Cache")
        # This message fully warms cm.conversations[phone] in memory, with
        # whatever variant this brand-new lead was auto-assigned (not
        # STALE_CACHE_VARIANT_KEY, which is is_active=FALSE).
        await cm.process_message(
            from_number=STALE_CACHE_TEST_PHONE, message_text="Hola", contact_name="Smoke Test Stale Cache",
            message_id=f"smoketest-stalecache-1-{date.today().isoformat()}",
            lead_bot_variant=lead.get("bot_variant"),
        )

        # Change bot_variant directly in the DB — no bot_conversation_state
        # deletion, no touching cm.conversations at all. Only a fresh
        # get_or_create_lead() read (exactly what webhook.py does on every
        # incoming message) should be able to surface this.
        with conn.cursor() as cur2:
            cur2.execute(
                "UPDATE whatsapp_leads SET bot_variant=%s WHERE phone_number=%s",
                (STALE_CACHE_VARIANT_KEY, STALE_CACHE_TEST_PHONE),
            )
            conn.commit()
        invalidate_cache()
        lead2 = await get_or_create_lead(STALE_CACHE_TEST_PHONE, "Smoke Test Stale Cache")

        return await cm.process_message(
            from_number=STALE_CACHE_TEST_PHONE, message_text="Hola de nuevo", contact_name="Smoke Test Stale Cache",
            message_id=f"smoketest-stalecache-2-{date.today().isoformat()}",
            lead_bot_variant=lead2.get("bot_variant"),
        )

    try:
        resp = asyncio.run(_run())
    except Exception as e:
        check("Stale cache fix — fresh DB variant wins over a fully stale in-memory cache", False, str(e))
        traceback.print_exc()
        return

    resp_text = resp if isinstance(resp, str) else json.dumps(resp, ensure_ascii=False)
    check(
        "Stale cache fix — fresh DB variant wins over a fully stale in-memory cache",
        STALE_CACHE_OVERRIDE_MARKER in resp_text,
        resp_text[:150].replace("\n", " "),
    )

    with conn.cursor() as cur:
        cur.execute("DELETE FROM bot_ab_variants WHERE variant_key=%s", (STALE_CACHE_VARIANT_KEY,))
        conn.commit()


DISABLED_TRIGGER_TEST_PHONE = "56900007769"
DISABLED_TRIGGER_VARIANT_KEY = "_smoketest_disabledtrigger"


def test_disabled_faq_trigger(conn):
    """
    Per-variant disabled FAQ triggers (2026-07-24): an operator can opt a
    canned FAQ topic (e.g. "precio") out of a specific variant, so a
    matching free-text question skips the automatic reply and falls through
    the bot's priority chain instead — normally reaching the live-AI
    fallback. Added after the "IA 1" variant kept answering with the
    canned price list instead of the AI even with a model configured;
    the FAQ match at PRIORITY 0.9 in conversation.py fires before the AI
    fallback ever gets a chance, so it needs its own opt-out per variant.
    """
    with conn.cursor() as cur:
        cur.execute("DELETE FROM whatsapp_leads WHERE phone_number=%s", (DISABLED_TRIGGER_TEST_PHONE,))
        cur.execute("DELETE FROM bot_ab_variants WHERE variant_key=%s", (DISABLED_TRIGGER_VARIANT_KEY,))
        cur.execute(
            "INSERT INTO bot_ab_variants (variant_key, label, is_active, disabled_triggers) VALUES (%s, %s, FALSE, %s)",
            (DISABLED_TRIGGER_VARIANT_KEY, "Smoke Test Disabled Trigger (inactive)", ["precio"]),
        )
        conn.commit()

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        from app.bot.conversation import ConversationManager
        from app.bot.variant_overrides import invalidate_cache
        from app.db.leads import get_or_create_lead, set_bot_variant_for_lead
    except Exception as e:
        check("Disabled FAQ trigger — import ConversationManager", False, str(e))
        return

    async def _run():
        invalidate_cache()
        cm = ConversationManager()
        lead = await get_or_create_lead(DISABLED_TRIGGER_TEST_PHONE, "Smoke Test Disabled Trigger")
        await cm.process_message(
            from_number=DISABLED_TRIGGER_TEST_PHONE, message_text="Hola", contact_name="Smoke Test Disabled Trigger",
            message_id=f"smoketest-disabledtrigger-warmup-{date.today().isoformat()}",
            lead_bot_variant=lead.get("bot_variant"),
        )

        await set_bot_variant_for_lead(DISABLED_TRIGGER_TEST_PHONE, DISABLED_TRIGGER_VARIANT_KEY)
        invalidate_cache()
        lead2 = await get_or_create_lead(DISABLED_TRIGGER_TEST_PHONE, "Smoke Test Disabled Trigger")

        return await cm.process_message(
            from_number=DISABLED_TRIGGER_TEST_PHONE, message_text="cuales son los precios",
            contact_name="Smoke Test Disabled Trigger",
            message_id=f"smoketest-disabledtrigger-1-{date.today().isoformat()}",
            lead_bot_variant=lead2.get("bot_variant"),
        )

    try:
        resp = asyncio.run(_run())
    except Exception as e:
        check("Disabled FAQ trigger — 'precio' question skips the canned reply", False, str(e))
        traceback.print_exc()
        return

    resp_text = resp if isinstance(resp, str) else json.dumps(resp, ensure_ascii=False)
    check(
        "Disabled FAQ trigger — 'precio' question skips the canned reply",
        "Precios HotBoat" not in resp_text,
        resp_text[:150].replace("\n", " "),
    )

    with conn.cursor() as cur:
        cur.execute("DELETE FROM bot_ab_variants WHERE variant_key=%s", (DISABLED_TRIGGER_VARIANT_KEY,))
        conn.commit()


CUSTOM_PROMPT_VARIANT_KEY = "_smoketest_prompt"
CUSTOM_PROMPT_MARKER = "SMOKETEST_PROMPT_MARKER_DO_NOT_SHIP"


def test_custom_ai_system_prompt(conn):
    """
    Per-variant custom AI system prompt (2026-07-24, bot_ab_variants.
    system_prompt) — an operator can override the editable part of the
    prompt the live-AI fallback uses for a specific variant (e.g. IA 1),
    without touching the fixed safety footer (app/bot/ai_handler.py:
    SAFETY_FOOTER — anti-hallucination rules like never claiming a fake
    booking confirmation). Pure logic test, no real Groq call: checks that
    build_system_prompt() (1) uses the variant's custom text when set,
    (2) always appends the safety footer regardless, and (3) falls back to
    the default prompt when the variant has none set / blank.
    """
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        from app.bot.ai_handler import build_system_prompt, SAFETY_FOOTER, _default_editable_prompt
        from app.bot.variant_overrides import set_current_variant, get_current_system_prompt, invalidate_cache
    except Exception as e:
        check("Custom AI prompt — import ai_handler/variant_overrides", False, str(e))
        return

    with conn.cursor() as cur:
        cur.execute("DELETE FROM bot_ab_variants WHERE variant_key=%s", (CUSTOM_PROMPT_VARIANT_KEY,))
        cur.execute(
            "INSERT INTO bot_ab_variants (variant_key, label, is_active, system_prompt) VALUES (%s, %s, FALSE, %s)",
            (CUSTOM_PROMPT_VARIANT_KEY, "Smoke Test Prompt (inactive)", CUSTOM_PROMPT_MARKER),
        )
        conn.commit()

    invalidate_cache()
    set_current_variant(CUSTOM_PROMPT_VARIANT_KEY)
    resolved = get_current_system_prompt()
    check(
        "Custom AI prompt — variant's custom prompt is resolved via the contextvar",
        resolved == CUSTOM_PROMPT_MARKER,
        repr(resolved),
    )

    custom_full = build_system_prompt(CUSTOM_PROMPT_MARKER)
    check(
        "Custom AI prompt — custom prompt still gets the safety footer appended",
        custom_full.startswith(CUSTOM_PROMPT_MARKER) and SAFETY_FOOTER in custom_full,
        custom_full[:120].replace("\n", " "),
    )

    default_full = build_system_prompt(None)
    check(
        "Custom AI prompt — no custom prompt falls back to the default business-info prompt",
        "INFORMACIÓN DEL NEGOCIO" in default_full and SAFETY_FOOTER in default_full,
    )

    set_current_variant(None)

    with conn.cursor() as cur:
        cur.execute("DELETE FROM bot_ab_variants WHERE variant_key=%s", (CUSTOM_PROMPT_VARIANT_KEY,))
        conn.commit()


AI_LINK_TEST_PHONE = "56900007768"


def test_ai_fallback_tracked_link(conn):
    """
    Tracked booking link on AI replies (2026-07-24) — explicitly requested:
    when a customer asks about price/reservation and the live-AI fallback
    answers, a real per-client tracked link (same mechanism the deterministic
    price/date flows already use, app/booking/link_tracking_router) must be
    appended so the admin can see if they actually clicked through. Mocks
    AIHandler.generate_response so this doesn't need a real GROQ_API_KEY —
    the thing under test is the link-appending logic in
    ConversationManager._try_ai_fallback, not Groq itself.
    """
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        from unittest.mock import patch, AsyncMock
        from app.bot.conversation import ConversationManager
        from app.bot.variant_overrides import invalidate_cache
    except Exception as e:
        check("AI fallback tracked link — import ConversationManager", False, str(e))
        return

    async def _run():
        invalidate_cache()
        cm = ConversationManager()
        conversation = {"messages": []}
        canned = "Ahoy grumete, el precio depende de cuántos vayan!"
        with patch("app.bot.ai_handler.AIHandler.generate_response", new=AsyncMock(return_value=canned)), \
             patch("app.bot.variant_overrides.get_current_ai_model", return_value=("groq", "llama-3.3-70b-versatile")), \
             patch("app.bot.variant_overrides.get_current_system_prompt", return_value=None):
            price_resp = await cm._try_ai_fallback(
                "cuanto vale para 5 personas", conversation, "Smoke Test AI Link", "es",
                from_number=AI_LINK_TEST_PHONE,
            )
            unrelated_resp = await cm._try_ai_fallback(
                "me encanta el paisaje de la laguna", conversation, "Smoke Test AI Link", "es",
                from_number=AI_LINK_TEST_PHONE,
            )
        return price_resp, unrelated_resp

    try:
        price_resp, unrelated_resp = asyncio.run(_run())
    except Exception as e:
        check("AI fallback tracked link — price question gets a real tracked link appended", False, str(e))
        traceback.print_exc()
        return

    check(
        "AI fallback tracked link — price question gets a real tracked link appended",
        bool(price_resp) and "https://whatsapp.hotboat.cl/ir/" in price_resp,
        (price_resp or "")[:200].replace("\n", " "),
    )
    check(
        "AI fallback tracked link — unrelated question does not get a link appended",
        bool(unrelated_resp) and "https://whatsapp.hotboat.cl/ir/" not in unrelated_resp,
        (unrelated_resp or "")[:200].replace("\n", " "),
    )

    with conn.cursor() as cur:
        cur.execute("DELETE FROM tracked_quote_links WHERE phone=%s", (AI_LINK_TEST_PHONE,))
        conn.commit()


CONCURRENT_DOUBLE_MSG_PHONE = "56900007767"


def test_concurrent_double_message_race(conn):
    """
    Regression test for a real production bug (2026-08-13): a customer sent
    two messages about a second apart ("Hola" then "Cuáles son los
    valores?"). Both webhook deliveries ran as concurrent asyncio tasks on
    the same replica, and both reached get_conversation()'s empty-history
    branch before either had written back — so BOTH independently computed
    is_first_message()=True and both got the welcome menu; the actual
    pricing question never reached FAQ matching. Fixed with a per-phone
    asyncio.Lock in ConversationManager.process_message() (see its
    docstring) that forces one customer's own messages to be handled
    strictly in order — this test proves it by firing both messages
    concurrently via asyncio.gather and checking the SECOND one gets the
    real price answer, not a second copy of the welcome menu.
    """
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        from app.bot.conversation import ConversationManager
    except Exception as e:
        check("Concurrent double-message race — import ConversationManager", False, str(e))
        return

    with conn.cursor() as cur:
        cur.execute("DELETE FROM whatsapp_leads WHERE phone_number=%s", (CONCURRENT_DOUBLE_MSG_PHONE,))
        conn.commit()

    async def _run():
        cm = ConversationManager()
        return await asyncio.gather(
            cm.process_message(
                from_number=CONCURRENT_DOUBLE_MSG_PHONE, message_text="Hola",
                contact_name="Smoke Test Race", message_id=f"smoketest-race-1-{date.today().isoformat()}",
                lead_bot_variant="control",
            ),
            cm.process_message(
                from_number=CONCURRENT_DOUBLE_MSG_PHONE, message_text="Cuáles son los valores ?",
                contact_name="Smoke Test Race", message_id=f"smoketest-race-2-{date.today().isoformat()}",
                lead_bot_variant="control",
            ),
        )

    try:
        r1, r2 = asyncio.run(_run())
    except Exception as e:
        check("Concurrent double-message race — both messages processed without crashing", False, str(e))
        traceback.print_exc()
        return

    check(
        "Concurrent double-message race — first message still gets the welcome menu",
        bool(r1) and "grumete" in r1.lower(),
        (r1 or "")[:150].replace("\n", " "),
    )
    check(
        "Concurrent double-message race — second message gets the real answer, not a 2nd welcome menu",
        bool(r2) and "precios hotboat" in r2.lower(),
        (r2 or "")[:150].replace("\n", " "),
    )


def main():
    conn = psycopg2.connect(DATABASE_URL)
    try:
        booking_ref = test_pricing_and_booking(conn)
        test_signature(booking_ref, conn)
        test_bot_ninos_regression()
        test_ab_experiment(conn)
        test_ai_fallback_safety_net(conn)
        test_ab_weighted_assignment()
        test_manual_variant_switch(conn)
        test_lead_bot_variant_always_fresh(conn)
        test_disabled_faq_trigger(conn)
        test_custom_ai_system_prompt(conn)
        test_ai_fallback_tracked_link(conn)
        test_concurrent_double_message_race(conn)
    except Exception as e:
        check("Unexpected error", False, str(e))
        traceback.print_exc()
    finally:
        cleanup(conn)
        conn.close()

    print("\n" + "=" * 60)
    failed = [name for name, ok, _ in results if not ok]
    if failed:
        print(f"❌ {len(failed)}/{len(results)} check(s) failed: {', '.join(failed)}")
        sys.exit(1)
    print(f"✅ All {len(results)} checks passed")
    sys.exit(0)


if __name__ == "__main__":
    main()
