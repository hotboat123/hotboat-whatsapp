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


def main():
    conn = psycopg2.connect(DATABASE_URL)
    try:
        booking_ref = test_pricing_and_booking(conn)
        test_signature(booking_ref, conn)
        test_bot_ninos_regression()
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
