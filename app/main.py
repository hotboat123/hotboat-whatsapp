"""
FastAPI main application - Updated 2026-03-08
"""
from fastapi import FastAPI, Request, Response, HTTPException, Query, UploadFile, Form, Header
from fastapi.responses import JSONResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import asyncio
import logging
import httpx

from app.booking.router import router as booking_router
from app.booking.admin_router import admin_router
from app.booking.content_router import content_router
from app.booking.signatures_router import signatures_router
from app.booking.stock_router import stock_router
from app.booking.financial_router import financial_router
from app.booking.bot_config_router import bot_config_router, _ensure_tables as _ensure_bot_tables, seed_defaults as seed_bot_defaults
from app.booking.gastos_router import gastos_router, _ensure_tables as _ensure_gastos_tables
from app.booking.tabla_router import tabla_router, _ensure_tabla_table, _seed_tabla_products, _ensure_catalog_table, _seed_catalog_defaults
from app.meta_pixel import apply_meta_pixel_placeholder, is_meta_pixel_enabled
from app.config import get_settings
from app.booking.operator_settings import get_setting as _get_operator_setting
from app.whatsapp.webhook import handle_webhook, verify_webhook
from app.whatsapp.client import whatsapp_client
from app.bot.conversation import ConversationManager
from app.db.queries import get_recent_conversations, get_appointments_between_dates, save_conversation, search_conversations_by_phone, search_messages_in_all_conversations_sync
from app.db.leads import (
    get_or_create_lead, 
    update_lead_status, 
    get_leads_by_status,
    get_conversation_history,
    import_conversation_batch,
    mark_conversation_as_read,
    update_lead_priority
)
from app.notifications import push_notifier
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pydantic import BaseModel
from typing import List, Optional, Dict

# Chilean timezone
CHILE_TZ = ZoneInfo("America/Santiago")
import os

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Reduce httpx logging noise (403 errors from expired media)
logging.getLogger("httpx").setLevel(logging.WARNING)

# ── In-memory log buffer (last 500 lines, queryable via /api/admin/logs) ──────
from app.log_buffer import install as _install_log_buffer
_install_log_buffer()

# Get settings
settings = get_settings()
if is_meta_pixel_enabled(settings.meta_pixel_id):
    logger.info(
        "Meta Pixel: enabled — HTML pages will include the base code (booking, pagar, chat, firma)."
    )
else:
    import os

    present = [
        k
        for k in ("META_PIXEL_ID", "FACEBOOK_PIXEL_ID", "FB_PIXEL_ID")
        if (os.environ.get(k) or "").strip() != ""
    ]
    if not present:
        msg = (
            "Meta Pixel: disabled — no META_PIXEL_ID / FACEBOOK_PIXEL_ID / FB_PIXEL_ID in "
            "this service's environment (check Railway → correct service + redeploy)."
        )
    else:
        msg = (
            "Meta Pixel: disabled — env var(s) set (%s) but value is not a usable numeric "
            "Pixel ID (copy only the digits from Events Manager; save + redeploy)."
            % ", ".join(present)
        )
    if settings.is_production:
        logger.warning(msg)
    else:
        logger.info(msg)

# ── Session auth ──────────────────────────────────────────────────────────────
import hmac as _hmac, hashlib as _hashlib, secrets as _secrets, time as _time

_SESSION_SECRET: str = ""

def _get_secret() -> str:
    global _SESSION_SECRET
    if not _SESSION_SECRET:
        _SESSION_SECRET = settings.session_secret or _secrets.token_hex(32)
    return _SESSION_SECRET

def _make_session_token(username: str) -> str:
    ts = str(int(_time.time()))
    payload = f"{username}:{ts}"
    sig = _hmac.new(_get_secret().encode(), payload.encode(), _hashlib.sha256).hexdigest()
    return f"{payload}:{sig}"

def _verify_session_token(token: str) -> bool:
    try:
        parts = token.rsplit(":", 1)
        if len(parts) != 2:
            return False
        payload, sig = parts
        expected = _hmac.new(_get_secret().encode(), payload.encode(), _hashlib.sha256).hexdigest()
        return _hmac.compare_digest(sig, expected)
    except Exception:
        return False

def _get_auth_cookie(request: Request) -> str | None:
    return request.cookies.get("kia_auth")

def _is_authenticated(request: Request) -> bool:
    token = _get_auth_cookie(request)
    return bool(token and _verify_session_token(token))

# ── Auto-sync background task ──────────────────────────────────────────────────
SYNC_INTERVAL_MINUTES = 30

async def _run_auto_sync():
    """Run all_appointments sync every SYNC_INTERVAL_MINUTES minutes."""
    from app.db.connection import get_connection
    from app.booking.admin_router import TABLE
    import re

    await asyncio.sleep(60)  # Wait 1 min after startup before first sync
    while True:
        try:
            logger.info(f"🔄 Auto-sync: sincronizando all_appointments...")
            from psycopg.types.json import Jsonb as PgJson

            def normalize_phone(ph):
                if not ph: return None
                ph = re.sub(r"[^\d+]", "", str(ph))
                if ph.startswith("+"): return ph
                if len(ph) == 9: return f"+56{ph}"
                if len(ph) == 11 and ph.startswith("56"): return f"+{ph}"
                return ph

            inserted_reservas = 0
            updated_reservas = 0
            status_updated = 0

            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT MAX(fecha) FROM reservas_con_extras")
                    cutoff = cur.fetchone()[0]
                    if not cutoff:
                        logger.warning("Auto-sync: reservas_con_extras is empty, skipping")
                        await asyncio.sleep(SYNC_INTERVAL_MINUTES * 60)
                        continue

                    # Sync reservas_con_extras → all_appointments (upsert)
                    cur.execute("""
                        SELECT id, appointment_id, fecha, hora, nombre_cliente, email, telefono,
                               servicio, num_personas, num_adultos, num_ninos,
                               ingreso_reserva, ingreso_extras, ingreso_total,
                               costo_operativo_fijo, costo_operativo_variable, costo_operativo_total,
                               ciudad_origen, como_supieron, clima_del_dia, categoria_clientes,
                               tipo_clientes, tiene_cruce, status, extras_json, created_at
                        FROM reservas_con_extras
                        ORDER BY fecha
                    """)
                    for row in cur.fetchall():
                        (rid, appt_id, fecha, hora, nombre, email, telefono,
                         servicio, num_p, num_adultos, num_ninos,
                         ing_res, ing_ext, ing_total, costo_fijo, costo_var, costo_total,
                         ciudad, como_sup, clima, categoria, tipo_cli, tiene_cruce,
                         status, extras, created) = row
                        # Check existing: sheets source_id first, then any source by appointment_id
                        existing = None
                        cur.execute(f"SELECT id FROM {TABLE} WHERE source='sheets' AND source_id=%s", (str(rid),))
                        existing = cur.fetchone()
                        if not existing and appt_id:
                            cur.execute(f"SELECT id FROM {TABLE} WHERE appointment_id=%s LIMIT 1", (str(appt_id),))
                            existing = cur.fetchone()

                        if existing:
                            cur.execute(f"""
                                UPDATE {TABLE}
                                SET extras_json=COALESCE(%s, extras_json),
                                    ingreso_extras=COALESCE(%s, ingreso_extras),
                                    ingreso_total=COALESCE(%s, ingreso_total),
                                    num_adultos=COALESCE(%s, num_adultos),
                                    num_ninos=COALESCE(%s, num_ninos),
                                    ciudad_origen=COALESCE(%s, ciudad_origen),
                                    como_supieron=COALESCE(%s, como_supieron),
                                    clima_del_dia=COALESCE(%s, clima_del_dia),
                                    categoria_clientes=COALESCE(%s, categoria_clientes),
                                    tipo_clientes=COALESCE(%s, tipo_clientes),
                                    tiene_cruce=COALESCE(%s, tiene_cruce),
                                    costo_operativo_variable=COALESCE(%s, costo_operativo_variable),
                                    costo_operativo_total=COALESCE(%s, costo_operativo_total),
                                    updated_at=NOW()
                                WHERE id=%s
                            """, (PgJson(extras) if extras else None,
                                  float(ing_ext) if ing_ext else None,
                                  float(ing_total) if ing_total else None,
                                  num_adultos, num_ninos, ciudad, como_sup, clima, categoria,
                                  tipo_cli, tiene_cruce,
                                  float(costo_var) if costo_var else None,
                                  float(costo_total) if costo_total else None,
                                  existing[0]))
                            updated_reservas += 1
                        else:
                            cur.execute(f"""
                                INSERT INTO {TABLE}
                                (source, source_id, appointment_id, fecha, hora,
                                 nombre_cliente, email, telefono, servicio, num_personas,
                                 num_adultos, num_ninos,
                                 ingreso_reserva, ingreso_extras, ingreso_total,
                                 costo_operativo_fijo, costo_operativo_variable, costo_operativo_total,
                                 ciudad_origen, como_supieron, clima_del_dia,
                                 categoria_clientes, tipo_clientes, tiene_cruce,
                                 status, extras_json, created_at, updated_at)
                                VALUES ('sheets',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
                                ON CONFLICT DO NOTHING
                            """, (str(rid), str(appt_id) if appt_id else None,
                                  fecha, hora, nombre, email,
                                  re.sub(r"[^\d+]", "", str(telefono)) if telefono else None,
                                  servicio or "HotBoat", str(num_p) if num_p else None,
                                  num_adultos, num_ninos,
                                  float(ing_res or 0), float(ing_ext or 0), float(ing_total or 0),
                                  float(costo_fijo or 0), float(costo_var or 0), float(costo_total or 0),
                                  ciudad, como_sup, clima, categoria, tipo_cli, tiene_cruce,
                                  status, PgJson(extras or {}), created))
                            inserted_reservas += 1

                    # Remove duplicates (old Reservas_Con_Extras_Sheets rows replaced by reservas_con_extras)
                    cur.execute("""
                        DELETE FROM all_appointments
                        WHERE source = 'sheets' AND appointment_id IS NOT NULL
                        AND id NOT IN (
                            SELECT MAX(id) FROM all_appointments
                            WHERE source = 'sheets' AND appointment_id IS NOT NULL
                            GROUP BY appointment_id
                        )
                    """)
                    dedup_deleted = cur.rowcount

                    conn.commit()

            logger.info(f"✅ Auto-sync OK: reservas({inserted_reservas} nuevas/{updated_reservas} actualizadas/{dedup_deleted} dedup), {status_updated} estados")

            # Clean up stale pending_payment web bookings (older than 45 min)
            try:
                with get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            DELETE FROM all_appointments
                            WHERE source = 'hotboat_web'
                              AND status = 'pending_payment'
                              AND created_at < NOW() - INTERVAL '45 minutes'
                        """)
                        deleted = cur.rowcount
                        conn.commit()
                if deleted:
                    logger.info(f"🗑️ Auto-cleanup: {deleted} pending_payment booking(s) > 45 min eliminados")
            except Exception as ce:
                logger.warning(f"Cleanup pending_payment error: {ce}")

        except Exception as e:
            logger.error(f"❌ Auto-sync error: {e}")

        await asyncio.sleep(SYNC_INTERVAL_MINUTES * 60)


async def _run_pending_payment_email_scheduler():
    """Every 3 minutes: send booking_created email to bookings still pending after 5 min."""
    await asyncio.sleep(60)  # short delay after startup
    while True:
        try:
            from app.booking.booking_email import run_pending_payment_email_sweep
            result = await asyncio.to_thread(run_pending_payment_email_sweep, 5)
            if result.get("sent", 0) or result.get("errors"):
                logger.info("📧 pending-payment sweep: %s", result)
        except Exception as _pe:
            logger.error("Pending-payment sweep error: %s", _pe)
        await asyncio.sleep(180)  # every 3 minutes


async def _run_email_sweeps_scheduler():
    """Run followup + birthday email sweeps every 30 min (DB flags ensure idempotency)."""
    await asyncio.sleep(120)  # brief delay after startup
    while True:
        try:
            from app.booking.booking_email import run_followup_email_sweep, run_birthday_email_sweep
            for fn, name in ((run_followup_email_sweep, "followup"), (run_birthday_email_sweep, "birthday")):
                try:
                    result = await asyncio.to_thread(fn)
                    if result.get("sent", 0) or result.get("errors"):
                        logger.info("📧 %s email sweep: %s", name, result)
                except Exception as _se:
                    logger.error("Email sweep %s error: %s", name, _se)
        except Exception as _fe:
            logger.error("Email sweeps scheduler error: %s", _fe)
        await asyncio.sleep(1800)  # re-check every 30 minutes


async def _run_daily_summary_scheduler():
    """Every morning at 08:00 Santiago time, send the day's booking summary to the operator."""
    from zoneinfo import ZoneInfo
    from datetime import datetime, timedelta, time as dtime
    CHILE_TZ = ZoneInfo("America/Santiago")
    SEND_HOUR = 8  # 08:00 Santiago

    while True:
        now = datetime.now(CHILE_TZ)
        target = now.replace(hour=SEND_HOUR, minute=0, second=0, microsecond=0)
        if now >= target:
            target += timedelta(days=1)
        wait_secs = (target - now).total_seconds()
        logger.info("📅 Daily summary scheduled in %.0f min (at %s Santiago)", wait_secs / 60, target.strftime("%H:%M %d/%m"))
        await asyncio.sleep(wait_secs)
        try:
            from app.booking.booking_email import send_daily_summary_email
            result = await asyncio.to_thread(send_daily_summary_email)
            logger.info("📅 Daily summary: %s", result)
        except Exception as _e:
            logger.error("Daily summary scheduler error: %s", _e)
        await asyncio.sleep(60)  # safety gap to avoid double-fire


async def _run_signature_summary_scheduler():
    """Every morning at 09:00 Santiago, send T&C signature summary for today's bookings."""
    from zoneinfo import ZoneInfo
    from datetime import datetime, timedelta
    CHILE_TZ = ZoneInfo("America/Santiago")
    SEND_HOUR = 9  # 09:00 Santiago

    while True:
        now = datetime.now(CHILE_TZ)
        target = now.replace(hour=SEND_HOUR, minute=0, second=0, microsecond=0)
        if now >= target:
            target += timedelta(days=1)
        wait_secs = (target - now).total_seconds()
        logger.info("✍️ Signature summary scheduled in %.0f min (at %s Santiago)", wait_secs / 60, target.strftime("%H:%M %d/%m"))
        await asyncio.sleep(wait_secs)
        try:
            from app.booking.signatures_email import run_daily_signature_summary_sweep
            result = await asyncio.to_thread(run_daily_signature_summary_sweep)
            logger.info("✍️ Signature summary sweep: %s", result)
        except Exception as _e:
            logger.error("Signature summary scheduler error: %s", _e)
        await asyncio.sleep(60)


async def _run_pre_booking_notif_scheduler():
    """Every 10 min: check for bookings starting in ~60 min and notify admin."""
    POLL_SECONDS = 600  # 10 minutes
    # Small initial delay so startup traffic settles before first check
    await asyncio.sleep(30)
    while True:
        try:
            from app.booking.signatures_email import run_pre_booking_notif_sweep
            result = await asyncio.to_thread(run_pre_booking_notif_sweep)
            if result.get("sent"):
                logger.info("⏰ Pre-booking notif sweep: %s", result)
        except Exception as _e:
            logger.error("Pre-booking notif scheduler error: %s", _e)
        await asyncio.sleep(POLL_SECONDS)


async def _run_yesterday_weekly_scheduler():
    """Every morning at 09:00 Santiago: send yesterday's bookings summary.
    On Mondays also send the weekly summary."""
    from zoneinfo import ZoneInfo
    from datetime import datetime, timedelta
    CHILE_TZ = ZoneInfo("America/Santiago")
    SEND_HOUR = 9  # 09:00 Santiago

    while True:
        now = datetime.now(CHILE_TZ)
        target = now.replace(hour=SEND_HOUR, minute=0, second=0, microsecond=0)
        if now >= target:
            target += timedelta(days=1)
        wait_secs = (target - now).total_seconds()
        logger.info("📬 Yesterday/weekly notif scheduled in %.0f min (at %s Santiago)", wait_secs / 60, target.strftime("%H:%M %d/%m"))
        await asyncio.sleep(wait_secs)
        try:
            from app.booking.booking_email import send_yesterday_summary_email, send_weekly_summary_email
            today = datetime.now(CHILE_TZ)
            result_daily = await asyncio.to_thread(send_yesterday_summary_email)
            logger.info("📬 Yesterday summary: %s", result_daily)
            if today.weekday() == 0:  # Monday
                result_weekly = await asyncio.to_thread(send_weekly_summary_email)
                logger.info("📆 Weekly summary: %s", result_weekly)
        except Exception as _e:
            logger.error("Yesterday/weekly summary scheduler error: %s", _e)
        await asyncio.sleep(60)


async def _run_stock_consume_scheduler():
    """
    Stock scheduler (Santiago time):
      • Every 15 min: consume stock for reservations that have already FINISHED
        (date + time + trip duration in the past), so a tabla is discounted
        shortly after that customer's reservation ends.
      • 09:00 and 21:00: send low-stock alert email if any product is below
        its minimum — twice a day avoids the inbox getting flooded every 15 min.
      • Once daily at 09:00: also check today's tabla ingredient shortfalls.
    Also runs once 45 s after startup to catch anything missed.
    """
    from zoneinfo import ZoneInfo
    from datetime import datetime
    CHILE_TZ = ZoneInfo("America/Santiago")

    CONSUME_INTERVAL_SECONDS = 15 * 60
    # Track the last (date, hour) pair for which each alert was sent
    # so it fires at most once per window, even if the loop drifts.
    last_morning_date = None   # 09:00 window
    last_evening_date = None   # 21:00 window

    # ── startup pass ──────────────────────────────────────────────────────────
    await asyncio.sleep(45)
    try:
        from app.booking.stock_router import auto_consume_past_bookings
        result = await asyncio.to_thread(auto_consume_past_bookings)
        logger.info("📦 Stock auto-consume (startup): %s", result)
    except Exception as _e:
        logger.warning("Stock auto-consume startup skipped: %s", _e)

    # ── periodic loop ─────────────────────────────────────────────────────────
    while True:
        # Consume finished reservations
        try:
            from app.booking.stock_router import auto_consume_past_bookings, _send_low_stock_alert
            result = await asyncio.to_thread(auto_consume_past_bookings)
            logger.info("📦 Stock auto-consume: %s", result)
        except Exception as _e:
            logger.error("Stock auto-consume scheduler error: %s", _e)
            result = {}

        now = datetime.now(CHILE_TZ)
        today = now.date()

        # ── Low-stock alert: 09:00 and 21:00 only ─────────────────────────────
        is_morning = now.hour == 9  and last_morning_date != today
        is_evening = now.hour == 21 and last_evening_date != today
        if is_morning or is_evening:
            low_alerts = result.get("low_stock_alerts", [])
            if low_alerts:
                try:
                    await asyncio.to_thread(_send_low_stock_alert, low_alerts)
                    logger.info("📧 Low-stock alert sent (%d productos) at %02d:xx",
                                len(low_alerts), now.hour)
                except Exception as _e:
                    logger.error("Low-stock alert send failed: %s", _e)
            if is_morning:
                last_morning_date = today
            if is_evening:
                last_evening_date = today

        # ── Morning tabla ingredient shortfall: 09:00 only ────────────────────
        if is_morning:
            try:
                from app.booking.stock_router import check_and_alert_tabla_ingredients
                await asyncio.to_thread(check_and_alert_tabla_ingredients)
            except Exception as _e:
                logger.error("Tabla ingredient check error: %s", _e)

        await asyncio.sleep(CONSUME_INTERVAL_SECONDS)


def _ensure_web_push_table():
    """Create web_push_subscriptions table if it doesn't exist."""
    try:
        from app.db.connection import get_connection
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS web_push_subscriptions (
                        id           SERIAL PRIMARY KEY,
                        endpoint     TEXT UNIQUE NOT NULL,
                        p256dh       TEXT NOT NULL,
                        auth         TEXT NOT NULL,
                        created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        last_used_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                """)
                conn.commit()
        logger.info("✅ web_push_subscriptions table ready")
    except Exception as e:
        logger.warning(f"web_push_subscriptions table setup failed: {e}")


def _ensure_extras_visibility_table():
    """Create extras_visibility table if it doesn't exist (survives Sheets re-sync)."""
    try:
        from app.db.connection import get_connection
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS extras_visibility (
                        extra_name_lower TEXT PRIMARY KEY,
                        show_in_booking  BOOLEAN NOT NULL DEFAULT FALSE,
                        sort_order       INTEGER NOT NULL DEFAULT 999,
                        description      TEXT,
                        precio_venta     INTEGER,
                        costo            INTEGER,
                        icon             TEXT,
                        updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                """)
                for col, definition in [
                    ("sort_order",      "INTEGER NOT NULL DEFAULT 999"),
                    ("description",     "TEXT"),
                    ("precio_venta",    "INTEGER"),
                    ("costo",           "INTEGER"),
                    ("icon",            "TEXT"),
                    ("name",            "TEXT"),
                    ("user_hidden",     "BOOLEAN NOT NULL DEFAULT FALSE"),
                    ("stock_product_id","INTEGER"),
                ]:
                    cur.execute(f"ALTER TABLE extras_visibility ADD COLUMN IF NOT EXISTS {col} {definition}")

                conn.commit()
        logger.info("✅ extras_visibility table ready")
    except Exception as e:
        logger.error(f"extras_visibility table init error: {e}")


_EXTRAS_SEED = [
    # (extra_name_lower, display_name, precio_venta, costo, icon, sort_order)
    ("tabla_4_personas",  "Tabla de Picoteo Grande (4 personas)",     25000,  0, "🍇",  1),
    ("tabla_2_personas",  "Tabla de Picoteo Pequeña (2 personas)",    20000,  0, "🍇",  2),
    ("jugo_natural",      "Jugo Natural 1L (piña o naranja)",         10000,  0, "🥤",  3),
    ("lata_bebida",       "Lata Bebida (Coca-Cola o Fanta)",           2900,  0, "🥤",  4),
    ("agua_mineral",      "Agua Mineral 1.5L",                         2500,  0, "💧",  5),
    ("helado",            "Helado Individual",                          3500,  0, "🍦",  6),
    ("modo_romantico",    "Modo Romántico (pétalos + decoración)",    25000,  0, "🌹",  7),
    ("velas_led",         "Velas LED Decorativas",                    10000,  0, "🕯️",  8),
    ("letras_luminosas",  "Letras Luminosas 'Te Amo' / 'Love'",       15000,  0, "✨",  9),
    ("pack_velas_letras", "Pack Nocturno Completo (velas + letras)",  20000,  0, "🌙", 10),
    ("video_15_seg",      "Video Personalizado 15s",                  30000,  0, "🎥", 11),
    ("video_1_min",       "Video Personalizado 60s",                  40000,  0, "🎥", 12),
    ("transporte",        "Transporte Ida y Vuelta desde Pucón",      50000,  0, "🚐", 13),
    ("toalla_normal",     "Toalla Normal",                             9000,  0, "🧻", 14),
    ("toalla_poncho",     "Toalla Poncho",                            10000,  0, "🧻", 15),
    ("chalas",            "Chalas de Ducha",                          10000,  0, "🩴", 16),
    ("reserva_flex",      "Reserva FLEX (+10%)",                          0,  0, "🔄", 17),
]


def _seed_extras_visibility():
    """Populate extras_visibility with the canonical catalog if still empty."""
    try:
        from app.db.connection import get_connection
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM extras_visibility")
                if cur.fetchone()[0] > 0:
                    return  # already seeded
                for (key, name, price, cost, icon, sort) in _EXTRAS_SEED:
                    cur.execute("""
                        INSERT INTO extras_visibility
                            (extra_name_lower, name, precio_venta, costo, icon,
                             sort_order, show_in_booking)
                        VALUES (%s, %s, %s, %s, %s, %s, TRUE)
                        ON CONFLICT DO NOTHING
                    """, (key, name, price, cost, icon, sort))
                conn.commit()
        logger.info("✅ extras_visibility seeded with %d items", len(_EXTRAS_SEED))
    except Exception as e:
        logger.warning("extras_visibility seed failed: %s", e)


_CLOTHING_PRODUCTS_SEED = [
    # (slug, display_name, stock_name, initial_stock, cost, price, icon, sort)
    ("polera_blanca",        "Polera Blanca",        "Polera Blanca",        10,  4141, 17990, "👕", 30),
    ("polera_negra",         "Polera Negra",         "Polera Negra",         12,  4141, 17990, "👕", 31),
    ("polera_verde",         "Polera Verde",         "Polera Verde",          6,  4141, 17990, "👕", 32),
    ("poleron_negro",        "Polerón Negro",        "Polerón Negro",         6,  8841, 29990, "🧥", 33),
    ("poleron_azul_marino",  "Polerón Azul Marino",  "Polerón Azul Marino",   6,  8841, 29990, "🧥", 34),
    ("poleron_grueso_negro", "Polerón Grueso Negro", "Polerón Grueso Negro",  6, 12841, 34990, "🧥", 35),
    ("gorro_verde",          "Gorro Verde",          "Gorro Verde",           8,  4304, 14990, "🧢", 36),
    ("gorro_blanco",         "Gorro Blanco",         "Gorro Blanco",          8,  4304, 14990, "🧢", 37),
    ("gorro_negro",          "Gorro Negro",          "Gorro Negro",           8,  4304, 14990, "🧢", 38),
]

# Old (wrong) costs seeded earlier, kept so we can self-heal rows that still
# carry them without clobbering any manual cost edit the admin may have made.
_CLOTHING_OLD_COSTS = {
    "polera_blanca": 15000, "polera_negra": 18000, "polera_verde": 9000,
    "poleron_negro": 9000, "poleron_azul_marino": 9000, "poleron_grueso_negro": 9000,
    "gorro_verde": 8000, "gorro_blanco": 8000, "gorro_negro": 8000,
}


def _fix_clothing_costs():
    """Correct clothing costs only where the row still holds the old wrong value."""
    try:
        from app.db.connection import get_connection
        seed_by_slug = {row[0]: row for row in _CLOTHING_PRODUCTS_SEED}
        with get_connection() as conn:
            with conn.cursor() as cur:
                for slug, old_cost in _CLOTHING_OLD_COSTS.items():
                    new_cost = seed_by_slug[slug][4]
                    cur.execute(
                        "UPDATE extras_visibility SET costo=%s "
                        "WHERE extra_name_lower=%s AND costo=%s",
                        (new_cost, slug, old_cost),
                    )
                    cur.execute(
                        "UPDATE stock_products SET cost_per_unit=%s, updated_at=NOW() "
                        "WHERE id=(SELECT stock_product_id FROM extras_visibility "
                        "         WHERE extra_name_lower=%s) AND cost_per_unit=%s",
                        (new_cost, slug, old_cost),
                    )
                conn.commit()
    except Exception as e:
        logger.warning("Clothing cost fix skipped: %s", e)


def _seed_clothing_products():
    """Seed ropa clothing items into stock_products + extras_visibility + extras_bom."""
    try:
        from app.db.connection import get_connection
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM extras_visibility WHERE extra_name_lower = 'polera_blanca'"
                )
                if cur.fetchone()[0] > 0:
                    return
                for (slug, name, sp_name, stock, cost, price, icon, sort) in _CLOTHING_PRODUCTS_SEED:
                    cur.execute(
                        """
                        INSERT INTO stock_products
                            (name, category, unit, current_stock, min_stock, cost_per_unit, is_active)
                        VALUES (%s, 'Ropa', 'unidad', %s, 1, %s, TRUE)
                        RETURNING id
                        """,
                        (sp_name, stock, cost),
                    )
                    product_id = cur.fetchone()[0]
                    cur.execute(
                        """
                        INSERT INTO extras_visibility
                            (extra_name_lower, name, precio_venta, costo, icon,
                             sort_order, show_in_booking, stock_product_id)
                        VALUES (%s, %s, %s, %s, %s, %s, FALSE, %s)
                        ON CONFLICT DO NOTHING
                        """,
                        (slug, name, price, cost, icon, sort, product_id),
                    )
                    cur.execute(
                        "INSERT INTO extras_bom (extra_slug, product_id, quantity) VALUES (%s, %s, 1)",
                        (slug, product_id),
                    )
                conn.commit()
        logger.info("✅ Clothing products seeded (%d items)", len(_CLOTHING_PRODUCTS_SEED))
    except Exception as e:
        logger.warning("Clothing products seed failed: %s", e)


_PACKS_CATALOG_SEED = [
    {
        "slug": "termas-angostura",
        "name": "Pack Termas Angostura",
        "icon": "♨️",
        "description": (
            "¿Te animas a una pausa?\n\n"
            "Escápate a una cabaña rodeada de bosque nativo, donde el tiempo se detiene. "
            "Durante dos noches disfrutarás de desayuno, almuerzo y cena en el restaurante "
            "del complejo, y de acceso ilimitado a las piscinas de aguas termales al aire libre.\n\n"
            "Y como broche de oro: la experiencia única e inigualable del HotBoat — una tinaja "
            "flotante que navega en medio de la laguna, rodeada de volcanes y bosque nativo. "
            "Una sensación que no encontrarás en ningún otro lugar del mundo."
        ),
        "personas": "2 personas",
        "price_from": 399990,
        "cost_from": 0,
        "includes": [
            "2 noches en Cabaña exclusiva Termas Angostura",
            "Acceso ilimitado a Termas Angostura",
            "Pensión completa (desayuno, almuerzo y cena)",
            "Paseo en HotBoat (2 personas)",
        ],
        "display_order": 4,
    },
]


def _seed_packs_catalog():
    """Insert canonical packs that don't yet exist in DB (ON CONFLICT DO NOTHING)."""
    import json as _json
    try:
        from app.db.connection import get_connection
        with get_connection() as conn:
            with conn.cursor() as cur:
                for p in _PACKS_CATALOG_SEED:
                    cur.execute(
                        """
                        INSERT INTO packs
                          (slug, name, icon, description, personas,
                           price_from, cost_from, includes,
                           is_active, display_order)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, TRUE, %s)
                        ON CONFLICT (slug) DO NOTHING
                        """,
                        (
                            p["slug"], p["name"], p["icon"], p["description"],
                            p["personas"], p["price_from"], p["cost_from"],
                            _json.dumps(p["includes"], ensure_ascii=False),
                            p["display_order"],
                        ),
                    )
        logger.info("✅ Packs catalog seeded")
    except Exception as _e:
        logger.warning(f"Pack catalog seed skipped: {_e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start background tasks on startup, cancel on shutdown."""
    _ensure_web_push_table()
    _ensure_extras_visibility_table()
    _seed_extras_visibility()
    _seed_clothing_products()
    _fix_clothing_costs()
    _seed_packs_catalog()
    try:
        from app.bot.cart import CartManager
        CartManager.refresh_prices_from_db()
    except Exception as _e:
        logger.warning(f"Cart price refresh skipped: {_e}")
    try:
        from app.booking.db import load_prices_from_db
        load_prices_from_db()
    except Exception as _e:
        logger.warning(f"Booking prices refresh skipped: {_e}")
    try:
        from app.booking.operator_settings import seed_email_workflow_defaults
        seed_email_workflow_defaults()
    except Exception as _e:
        logger.warning(f"Email workflow seed skipped: {_e}")
    # Apply any missing DB columns (idempotent migrations)
    try:
        from app.booking.db import ensure_db_columns
        ensure_db_columns()
        logger.info("✅ DB columns ensured (customer_language, pre_booking_notif_sent_at, extra_images)")
    except Exception as _e:
        logger.warning(f"ensure_db_columns skipped: {_e}")
    # Ensure signatures table exists
    try:
        from app.booking.db import ensure_signatures_table
        ensure_signatures_table()
    except Exception as _e:
        logger.warning(f"ensure_signatures_table skipped: {_e}")
    try:
        _ensure_bot_tables()
        seed_bot_defaults()
    except Exception as _e:
        logger.warning(f"bot config setup skipped: {_e}")
    try:
        _ensure_gastos_tables()
    except Exception as _e:
        logger.warning(f"gastos tables setup skipped: {_e}")
    try:
        _ensure_tabla_table()
        _seed_tabla_products()
        _ensure_catalog_table()
        _seed_catalog_defaults()
    except Exception as _e:
        logger.warning(f"tabla table setup skipped: {_e}")

    sync_task       = asyncio.create_task(_run_auto_sync())
    email_task      = asyncio.create_task(_run_email_sweeps_scheduler())
    pending_task    = asyncio.create_task(_run_pending_payment_email_scheduler())
    daily_task      = asyncio.create_task(_run_daily_summary_scheduler())
    sig_task        = asyncio.create_task(_run_signature_summary_scheduler())
    prebooking_task = asyncio.create_task(_run_pre_booking_notif_scheduler())
    notif_task      = asyncio.create_task(_run_yesterday_weekly_scheduler())
    stock_task      = asyncio.create_task(_run_stock_consume_scheduler())
    logger.info(f"🕐 Auto-sync iniciado: cada {SYNC_INTERVAL_MINUTES} minutos")
    logger.info("📧 Email sweeps scheduler iniciado (followup + birthday, cada 30 min)")
    logger.info("📧 Pending-payment email sweep iniciado (cada 3 min, delay 5 min)")
    logger.info("📅 Daily summary scheduler iniciado (08:00 Santiago)")
    logger.info("✍️ Signature summary scheduler iniciado (09:00 Santiago)")
    logger.info("⏰ Pre-booking notif scheduler iniciado (cada 10 min, 60 min antes)")
    logger.info("📬 Yesterday/weekly notif scheduler iniciado (09:00 Santiago, lunes también semanal)")
    yield
    for task in (sync_task, email_task, pending_task, daily_task, sig_task, prebooking_task, notif_task, stock_task):
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    logger.info("🛑 Background tasks detenidos")


# Create FastAPI app
app = FastAPI(
    title="HotBoat WhatsApp Bot",
    description="Bot de WhatsApp para Hot Boat Chile",
    version="1.0.0",
    lifespan=lifespan,
)

# Add middleware to prevent caching of static files
@app.middleware("http")
async def add_no_cache_headers(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# Mount static files for Kia-Ai interface
static_dir = os.path.join(os.path.dirname(__file__), "static")
logger.info(f"📁 Static directory expected at: {static_dir}")
if os.path.exists(static_dir):
    logger.info(f"✅ Static directory found with files: {os.listdir(static_dir)}")
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
else:
    logger.warning("⚠️ Static directory not found – Kia-Ai UI will not be served.")

# Serve media files (images, PDFs, docs) for booking platform
media_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "media")
if os.path.exists(media_dir):
    app.mount("/media", StaticFiles(directory=media_dir), name="media")
    logger.info("✅ Media directory mounted at /media")

# Initialize conversation manager
conversation_manager = ConversationManager()
app.include_router(booking_router)
app.include_router(admin_router)
app.include_router(content_router)
app.include_router(signatures_router)
app.include_router(stock_router)
app.include_router(financial_router)
app.include_router(bot_config_router)
app.include_router(gastos_router)
app.include_router(tabla_router)


def _serve_chat_html() -> HTMLResponse:
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    index_path = os.path.join(static_dir, "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        body = apply_meta_pixel_placeholder(f.read(), settings.meta_pixel_id)
    return HTMLResponse(content=body)

def _serve_login_html(next_url: str = "/") -> HTMLResponse:
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=f"/login?next={next_url}", status_code=302)

@app.get("/login", response_class=HTMLResponse)
async def login_page():
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    login_path = os.path.join(static_dir, "login.html")
    with open(login_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

class LoginRequest(BaseModel):
    username: str
    password: str
    next: str = "/"

@app.post("/api/auth/login")
async def auth_login(req: LoginRequest):
    if req.username == settings.chat_username and req.password == settings.chat_password:
        token = _make_session_token(req.username)
        redirect = req.next if req.next.startswith("/") else "/"
        response = JSONResponse({"redirect": redirect})
        response.set_cookie(
            key="kia_auth",
            value=token,
            max_age=60 * 60 * 24 * 30,  # 30 days
            httponly=True,
            samesite="lax",
            secure=settings.is_production,
        )
        return response
    raise HTTPException(status_code=401, detail="Credenciales incorrectas")

@app.get("/logout")
async def logout():
    from fastapi.responses import RedirectResponse
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("kia_auth")
    return response

@app.post("/api/admin/chat-login")
async def admin_chat_login(x_admin_key: str = Header("")):
    """Sets kia_auth cookie when called with a valid admin key (for WhatsApp iframe)."""
    import json as _json
    master_key = os.environ.get("ADMIN_MASTER_KEY", "")
    if master_key and x_admin_key == master_key:
        valid = True
    else:
        raw = _get_operator_setting("admin_users") or "[]"
        users = _json.loads(raw)
        valid = not users or any(u.get("key") == x_admin_key for u in users)
    if not valid:
        raise HTTPException(status_code=401)
    token = _make_session_token("admin")
    response = JSONResponse({"ok": True})
    response.set_cookie(key="kia_auth", value=token, max_age=60*60*24*30,
                        httponly=True, samesite="lax", secure=settings.is_production)
    return response

@app.get("/", response_class=HTMLResponse)
async def root():
    """Admin panel — auth handled client-side via x-admin-key"""
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    path = os.path.join(static_dir, "admin-bookings.html")
    with open(path, encoding="utf-8") as f:
        return HTMLResponse(f.read())

@app.get("/admin", response_class=HTMLResponse)
async def admin_redirect():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/", status_code=302)

@app.get("/chat", response_class=HTMLResponse)
async def chat_ui(request: Request):
    """Serve WhatsApp chat interface"""
    if not _is_authenticated(request):
        return _serve_login_html("/chat")
    return _serve_chat_html()


@app.get("/pagar", response_class=HTMLResponse)
async def pago_page():
    """Serve branded payment landing page"""
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    path = os.path.join(static_dir, "pagar.html")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            content = apply_meta_pixel_placeholder(f.read(), settings.meta_pixel_id)
        return HTMLResponse(content=content)
    return HTMLResponse("<h1>Página no encontrada</h1>", status_code=404)


@app.get("/api/pago/order/{order_id}")
async def pago_order_proxy(order_id: int):
    """
    Proxy that fetches order details from WooCommerce and returns
    friendly data for the /pagar page.
    """
    try:
        from app.payment.woocommerce import get_order, WOO_URL
        data = await get_order(order_id)
        # Extract HotBoat-specific meta
        meta_map = {m["key"]: m["value"] for m in data.get("meta_data", [])}
        fee_lines = data.get("fee_lines", [])
        # Parse fecha / personas from fee_line name e.g.
        # "Reserva HotBoat – 4 personas (2026-05-31)"
        import re
        fee_name = fee_lines[0]["name"] if fee_lines else ""
        match_p = re.search(r'(\d+)\s*persona', fee_name)
        match_f = re.search(r'\((\d{4}-\d{2}-\d{2})\)', fee_name)
        extras_names = [fl["name"] for fl in fee_lines[1:]] if len(fee_lines) > 1 else []
        return {
            "order_id":   order_id,
            "status":     data.get("status"),
            "total":      data.get("total"),
            "payment_url": data.get("payment_url") or
                f"{WOO_URL}/checkout/order-pay/{order_id}/?pay_for_order=true&key={data.get('order_key','')}",
            "billing":    data.get("billing", {}),
            "fee_lines":  [{"name": fl["name"], "total": fl.get("total","0")} for fl in fee_lines],
            "meta": {
                "fecha":    match_f.group(1) if match_f else meta_map.get("hotboat_fecha",""),
                "personas": match_p.group(1) if match_p else "",
                "extras":   ", ".join(extras_names) if extras_names else "",
                "hora":     meta_map.get("hotboat_hora",""),
            },
        }
    except Exception as e:
        logger.warning(f"pago_order_proxy error for order {order_id}: {e}")
        return {}


@app.get("/sw.js")
async def serve_service_worker():
    """Serve service worker at root scope for full-app push notification support."""
    from fastapi.responses import FileResponse
    sw_path = os.path.join(os.path.dirname(__file__), "static", "sw.js")
    return FileResponse(sw_path, media_type="application/javascript", headers={
        "Service-Worker-Allowed": "/",
        "Cache-Control": "no-cache",
    })


@app.get("/manifest.json")
async def serve_manifest():
    """Serve PWA manifest at root."""
    from fastapi.responses import FileResponse
    manifest_path = os.path.join(os.path.dirname(__file__), "static", "manifest.json")
    return FileResponse(manifest_path, media_type="application/manifest+json")


class PushSubscribeRequest(BaseModel):
    endpoint: str
    keys: dict  # { p256dh: str, auth: str }


@app.post("/api/push/subscribe")
async def push_subscribe(request: PushSubscribeRequest):
    """Register a Web Push subscription."""
    from app.notifications import push_notifier
    logger.info("📲 Push subscribe request — endpoint: %s...", request.endpoint[:60])
    ok = await push_notifier.register_subscription(
        endpoint=request.endpoint,
        p256dh=request.keys.get("p256dh", ""),
        auth=request.keys.get("auth", ""),
    )
    logger.info("📲 Push subscribe result: %s", "OK" if ok else "FAILED")
    return {"status": "ok" if ok else "error"}


@app.delete("/api/push/subscribe")
async def push_unsubscribe(request: Request):
    """Remove a Web Push subscription."""
    from app.notifications import push_notifier
    data = await request.json()
    ok = await push_notifier.unregister_subscription(data.get("endpoint", ""))
    return {"status": "ok" if ok else "error"}


@app.get("/api/push/vapid-public-key")
async def get_vapid_public_key():
    """Return the VAPID public key so the frontend can subscribe."""
    return {"publicKey": settings.vapid_public_key or ""}


@app.get("/api/push/test")
@app.post("/api/push/test")
async def push_test():
    """Send a test push notification — GET or POST for easy browser testing."""
    from app.notifications import push_notifier as _pn
    subs = await _pn._get_subscriptions()
    if not subs:
        return {"sent": False, "subscriptions": 0, "error": "No subscriptions registered"}
    errors = []
    sent = 0
    from app.notifications.push_notifier import _send_web_push_sync_verbose
    for sub in subs:
        try:
            def _try_send(s=sub):
                return _send_web_push_sync_verbose(
                    s,
                    {"title": "🔔 Notificación de prueba", "body": "Si ves esto, ¡funcionan! ✅", "phone": None},
                    _pn._private_key,
                )
            ok = await asyncio.to_thread(_try_send)
            if ok:
                sent += 1
        except Exception as e:
            errors.append({"endpoint": sub.get("endpoint", "")[:50], "error": str(e)})
    return {"sent": sent > 0, "subscriptions": len(subs), "sent_count": sent, "errors": errors}


@app.get("/api/push/debug")
async def push_debug():
    """Diagnose Web Push configuration."""
    # Check pywebpush
    try:
        import pywebpush  # noqa
        pw_ok = True
        pw_version = getattr(pywebpush, "__version__", "installed")
    except ImportError as e:
        pw_ok = False
        pw_version = str(e)

    # Check subscriptions
    try:
        from app.notifications import push_notifier as _pn
        subs = await _pn._get_subscriptions()
        sub_count = len(subs)
        sub_sample = subs[0]["endpoint"][:60] + "..." if subs else None
    except Exception as e:
        sub_count = -1
        sub_sample = str(e)

    return {
        "vapid_private_key_set": bool(settings.vapid_private_key),
        "vapid_public_key_set": bool(settings.vapid_public_key),
        "pywebpush_installed": pw_ok,
        "pywebpush_version": pw_version,
        "subscriptions_count": sub_count,
        "subscription_endpoint_sample": sub_sample,
        "notifier_enabled": bool(settings.vapid_private_key),
    }


@app.get("/health")
async def health():
    """Detailed health check"""
    environment_status = "🚀 PRODUCTION" if settings.is_production else "🧪 STAGING" if settings.is_staging else "💻 DEVELOPMENT"
    return {
        "status": "healthy",
        "environment": settings.environment,
        "environment_status": environment_status,
        "bot_name": settings.bot_name,
        "database": "connected",  # TODO: Add real DB check
        "whatsapp_api": "configured"
    }


@app.get("/webhook")
async def webhook_verify(request: Request):
    """
    Webhook verification endpoint for WhatsApp
    Meta will call this to verify the webhook
    """
    try:
        # Get query parameters
        mode = request.query_params.get("hub.mode")
        token = request.query_params.get("hub.verify_token")
        challenge = request.query_params.get("hub.challenge")
        
        logger.info(f"Webhook verification request: mode={mode}, token={'***' if token else None}")
        
        # Verify the request
        if verify_webhook(mode, token, settings.whatsapp_verify_token):
            logger.info("✅ Webhook verified successfully")
            return Response(content=challenge, media_type="text/plain")
        else:
            logger.warning("❌ Webhook verification failed")
            raise HTTPException(status_code=403, detail="Verification failed")
            
    except Exception as e:
        logger.error(f"Error in webhook verification: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/webhook")
async def webhook_receive(request: Request):
    """
    Webhook endpoint to receive WhatsApp messages
    """
    try:
        # Get the request body
        body = await request.json()
        
        logger.info(f"📩 Received webhook: {body}")
        
        # Process the webhook
        result = await handle_webhook(body, conversation_manager)
        
        # WhatsApp expects a 200 OK response quickly
        return JSONResponse(content={"status": "ok"}, status_code=200)
        
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        # Still return 200 to WhatsApp to avoid retries
        return JSONResponse(content={"status": "error", "message": str(e)}, status_code=200)


@app.get("/conversations")
async def list_conversations(limit: int = 50):
    """List recent conversations (for admin dashboard)"""
    try:
        conversations = await get_recent_conversations(limit=limit)
        return {
            "conversations": conversations,
            "total": len(conversations)
        }
    except Exception as e:
        logger.error(f"Error listing conversations: {e}")
        return {
            "conversations": [],
            "total": 0,
            "error": str(e)
        }


@app.get("/appointments")
async def list_appointments(days_ahead: int = 30):
    """List appointments for the next N days"""
    try:
        start_date = datetime.now(CHILE_TZ)
        end_date = start_date + timedelta(days=days_ahead)
        appointments = await get_appointments_between_dates(start_date, end_date)
        return {
            "appointments": appointments,
            "total": len(appointments),
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat()
        }
    except Exception as e:
        logger.error(f"Error listing appointments: {e}")
        return {
            "appointments": [],
            "total": 0,
            "error": str(e)
        }


# Leads Management Endpoints

@app.get("/leads")
async def list_leads(lead_status: Optional[str] = None, limit: int = 50):
    """List leads, optionally filtered by status"""
    try:
        leads = await get_leads_by_status(lead_status=lead_status, limit=limit)
        return {
            "leads": leads,
            "total": len(leads),
            "filter": lead_status if lead_status else "all"
        }
    except Exception as e:
        logger.error(f"Error listing leads: {e}")
        return {
            "leads": [],
            "total": 0,
            "error": str(e)
        }


@app.get("/leads/{phone_number}")
async def get_lead_info(phone_number: str):
    """Get lead information and conversation history"""
    try:
        lead = await get_or_create_lead(phone_number)
        history = await get_conversation_history(phone_number, limit=100)
        
        return {
            "lead": lead,
            "conversation_count": len(history),
            "recent_messages": history[-10:] if history else []  # Last 10 messages
        }
    except Exception as e:
        logger.error(f"Error getting lead info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class LeadStatusUpdate(BaseModel):
    lead_status: str  # 'potential_client', 'bad_lead', 'customer', 'unknown'
    notes: Optional[str] = None


@app.put("/leads/{phone_number}/status")
async def update_lead(phone_number: str, update: LeadStatusUpdate):
    """Update lead classification status"""
    try:
        success = await update_lead_status(
            phone_number=phone_number,
            lead_status=update.lead_status,
            notes=update.notes
        )
        
        if success:
            return {
                "status": "updated",
                "phone_number": phone_number,
                "lead_status": update.lead_status
            }
        else:
            raise HTTPException(status_code=400, detail="Failed to update lead status")
    except Exception as e:
        logger.error(f"Error updating lead status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class BotToggleUpdate(BaseModel):
    bot_enabled: bool


@app.put("/leads/{phone_number}/bot-toggle")
async def toggle_bot_for_lead_endpoint(phone_number: str, update: BotToggleUpdate):
    """Enable or disable automatic bot responses for a specific lead"""
    try:
        from app.db.leads import toggle_bot_for_lead
        
        success = await toggle_bot_for_lead(
            phone_number=phone_number,
            bot_enabled=update.bot_enabled
        )
        
        if success:
            return {
                "status": "updated",
                "phone_number": phone_number,
                "bot_enabled": update.bot_enabled,
                "message": f"Bot {'enabled' if update.bot_enabled else 'disabled'} for {phone_number}"
            }
        else:
            raise HTTPException(status_code=400, detail="Failed to toggle bot for lead")
    except Exception as e:
        logger.error(f"Error toggling bot for lead: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/conversations/{phone_number}/mark-read")
async def mark_conversation_read(phone_number: str):
    """Mark a conversation as read (reset unread counter)"""
    try:
        success = await mark_conversation_as_read(phone_number)
        
        if success:
            return {
                "status": "success",
                "phone_number": phone_number,
                "message": "Conversation marked as read"
            }
        else:
            raise HTTPException(status_code=400, detail="Failed to mark conversation as read")
    except Exception as e:
        logger.error(f"Error marking conversation as read: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class PriorityUpdate(BaseModel):
    priority: int  # 0 = none, 1 = high, 2 = medium, 3 = low, 4 = "Ya reservó"


@app.put("/api/conversations/{phone_number}/priority")
async def update_conversation_priority(phone_number: str, update: PriorityUpdate):
    """Update conversation priority level"""
    try:
        success = await update_lead_priority(
            phone_number=phone_number,
            priority=update.priority
        )
        
        if success:
            return {
                "status": "success",
                "phone_number": phone_number,
                "priority": update.priority,
                "message": f"Priority updated to {update.priority}"
            }
        else:
            raise HTTPException(status_code=400, detail="Failed to update priority")
    except Exception as e:
        logger.error(f"Error updating priority: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _get_bot_response_content(response_key: str, lang: str = "es") -> Optional[str]:
    """Return bot response content from DB for the given key and language, or None if not set."""
    try:
        from app.db.connection import get_connection
        col = {"es": "content_es", "en": "content_en", "pt": "content_pt"}.get(lang, "content_es")
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SELECT {col}, content_es FROM bot_responses WHERE response_key = %s", (response_key,))
                row = cur.fetchone()
        if row:
            return row[0] or row[1]  # fallback to es if requested lang is empty
    except Exception:
        pass
    return None


class QuickReplyRequest(BaseModel):
    menu_option: int
    translate_to: Optional[str] = None  # "en", "pt", "fr" or None


def _translate_text(text: str, target_lang: str) -> str:
    """Translate text using Groq LLM (synchronous helper for quick-reply flow)."""
    lang_names = {"en": "English", "pt": "Portuguese (Brazilian)", "fr": "French", "es": "Spanish"}
    lang_name = lang_names.get(target_lang)
    if not lang_name:
        return text
    try:
        from openai import OpenAI as _OAI
        client = _OAI(api_key=settings.groq_api_key, base_url="https://api.groq.com/openai/v1")
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": f"You are a translator. Translate the user's message to {lang_name}. Return ONLY the translated text, no explanations, no quotes."},
                {"role": "user", "content": text},
            ],
            max_tokens=1024,
            temperature=0.1,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.warning(f"Translation error (falling back to original): {e}")
        return text


@app.post("/api/conversations/{phone_number}/quick-reply")
async def send_quick_reply(phone_number: str, request: QuickReplyRequest):
    """Send automatic menu response to conversation"""
    try:
        from app.bot.faq import FAQHandler
        from app.bot.translations import get_text
        
        # Use the GLOBAL conversation_manager so metadata persists for the webhook
        conv_manager = conversation_manager
        faq_handler = FAQHandler()
        
        # Get lead info first (without updating name)
        lead = await get_or_create_lead(phone_number)
        customer_name = lead.get('customer_name', phone_number)
        
        # Get or create conversation with the correct customer name
        conversation = await conv_manager.get_conversation(phone_number, customer_name)
        language = conversation.get("metadata", {}).get("language", "es")

        # Determine response based on menu option
        response_text = ""
        menu_option = request.menu_option
        tgt_lang = (request.translate_to or "").strip().lower() or None

        async def _send(msg: str) -> None:
            """Translate (if requested) then send a WhatsApp text message."""
            out = await asyncio.to_thread(_translate_text, msg.strip(), tgt_lang) if tgt_lang else msg.strip()
            await whatsapp_client.send_text_message(to=phone_number, message=out)
            await save_conversation(phone_number=phone_number, customer_name=customer_name,
                                    message_text="", response_text=out,
                                    message_type="text", direction="outgoing")
            conversation["messages"].append({"role": "assistant", "content": out,
                                             "timestamp": datetime.now(CHILE_TZ).isoformat()})

        if menu_option == 0:
            # Saludo de Tomás — secuencia de 4 mensajes con pequeño delay entre cada uno
            first_name = customer_name.split()[0] if customer_name else customer_name
            sequence = [
                f"Hola {first_name}! 👋",
                "Cómo estas?",
                "soy Tomás de Hotboat, soy humano 🙂",
                "Cualquier duda aquí estamos para ayudar 🙌",
            ]
            for i, msg in enumerate(sequence):
                if i > 0:
                    await asyncio.sleep(1.5)
                await _send(msg)
            conversation["last_interaction"] = datetime.now(CHILE_TZ).isoformat()
            return {"status": "success", "phone_number": phone_number,
                    "menu_option": menu_option,
                    "message_sent": f"Secuencia de {len(sequence)} mensajes enviada",
                    "whatsapp_response": {}}
        elif menu_option == 1:
            # Disponibilidad y horarios
            response_text = conv_manager._ask_for_reservation_date(conversation, language)
        elif menu_option == 2:
            # Precios por persona
            response_text = _get_bot_response_content("precio", language) or faq_handler.get_response("precio", language)
        elif menu_option == 3:
            # Características del HotBoat
            response_text = _get_bot_response_content("caracteristicas", language) or faq_handler.get_response("caracteristicas", language)
        elif menu_option == 4:
            # Extras y promociones
            conversation["metadata"]["awaiting_extra_selection"] = True
            response_text = faq_handler.get_response("extras", language)
        elif menu_option == 5:
            # Ubicación y reseñas
            response_text = _get_bot_response_content("ubicación", language) or faq_handler.get_response("ubicación", language)
        elif menu_option == 6:
            # Alojamientos — equivale al flujo menú 6
            from app.utils.media_handler import get_alojamientos_images
            text_intro = get_text("accommodations_only_intro", language)
            await whatsapp_client.send_text_message(to=phone_number, message=text_intro)
            await save_conversation(
                phone_number=phone_number, customer_name=customer_name,
                message_text="", response_text=text_intro,
                message_type="text", direction="outgoing"
            )
            conversation["messages"].append({
                "role": "assistant", "content": text_intro,
                "timestamp": datetime.now(CHILE_TZ).isoformat()
            })
            image_paths = get_alojamientos_images()
            for idx, image_path in enumerate(image_paths, 1):
                try:
                    media_id_img = await whatsapp_client.upload_media(image_path, mime_type="image/jpeg")
                    if media_id_img:
                        caption = "📄 Información completa de alojamientos" if idx == 1 else None
                        await whatsapp_client.send_image_message(
                            to=phone_number, media_id=media_id_img, caption=caption
                        )
                        await asyncio.sleep(0.5)
                except Exception as img_err:
                    logger.warning(f"Could not send alojamiento image {idx}: {img_err}")
            conversation["metadata"]["accommodation_flow"] = {
                "step": "choosing_property", "property": None,
                "room_type": None, "guests": None,
                "checkin_date": None, "checkout_date": None,
            }
            for key in ("awaiting_packages_submenu", "experience_flow", "complete_packages_flow", "build_package_flow"):
                conversation["metadata"].pop(key, None)
            conversation["last_interaction"] = datetime.now(CHILE_TZ).isoformat()
            return {
                "status": "success", "phone_number": phone_number,
                "menu_option": menu_option,
                "message_sent": f"Alojamientos: texto + {len(image_paths)} imágenes enviadas",
                "whatsapp_response": {}
            }
        elif menu_option == 8:
            # Packs Completos — equivale al flujo menú 7 → 1
            import os
            from app.utils.media_handler import PACKS_IMAGES_DIR
            pack_text = get_text("complete_packages_menu", language)
            resumen_path = os.path.join(PACKS_IMAGES_DIR, "resumen-packs.jpg")
            if os.path.exists(resumen_path):
                try:
                    media_id_img = await whatsapp_client.upload_media(resumen_path, mime_type="image/jpeg")
                    if media_id_img:
                        await whatsapp_client.send_image_message(
                            to=phone_number,
                            media_id=media_id_img,
                            caption="📦 Packs Completos HotBoat"
                        )
                        await asyncio.sleep(0.5)
                except Exception as img_err:
                    logger.warning(f"Could not send packs image: {img_err}")
            # Send the packs menu text
            await whatsapp_client.send_text_message(to=phone_number, message=pack_text)
            await save_conversation(
                phone_number=phone_number,
                customer_name=customer_name,
                message_text="",
                response_text=pack_text,
                message_type="text",
                direction="outgoing"
            )
            conversation["messages"].append({
                "role": "assistant",
                "content": pack_text,
                "timestamp": datetime.now(CHILE_TZ).isoformat()
            })
            # Set complete_packages_flow so the bot continues when user replies
            conversation["metadata"]["complete_packages_flow"] = {"step": "selecting_type"}
            # Clear any conflicting flows
            for key in ("awaiting_packages_submenu", "accommodation_flow", "experience_flow", "build_package_flow"):
                conversation["metadata"].pop(key, None)
            conversation["last_interaction"] = datetime.now(CHILE_TZ).isoformat()
            return {
                "status": "success",
                "phone_number": phone_number,
                "menu_option": menu_option,
                "message_sent": "Packs Completos: imagen + texto enviados",
                "whatsapp_response": {}
            }
        elif menu_option == 10:
            # Bebestibles — opciones para celebrar (solo adultos)
            response_text = _get_bot_response_content("bebestibles", language) or (
                "🍷 *Opciones para celebrar* (solo adultos)\n\n"
                "$6.000 → Cerveza artesanal 330ml\n"
                "$15.000 → Vino reserva\n"
                "$26.000 → Champaña Riccadonna\n"
                "$20.000 → Pack de 4 cervezas artesanales"
            )
        elif menu_option == 9:
            # Alojamientos — read from bot_responses so it's editable from admin panel
            _col9 = {"en": "content_en", "pt": "content_pt"}.get(language, "content_es")
            _db9  = None
            try:
                from app.db.connection import get_connection as _gc9
                with _gc9() as _c9:
                    with _c9.cursor() as _cur9:
                        _cur9.execute(
                            f"SELECT COALESCE({_col9}, content_es) FROM bot_responses "
                            "WHERE menu_option = %s AND active = TRUE LIMIT 1",
                            (menu_option,)
                        )
                        _r9 = _cur9.fetchone()
                        if _r9 and _r9[0]:
                            _db9 = _r9[0]
            except Exception as _e9:
                logger.warning(f"alojamientos quick-reply DB lookup failed: {_e9}")
            response_text = _db9 or (
                "🏠 Para ver nuestros alojamientos disponibles y hacer tu reserva, visita nuestra página de reservas:\n\n"
                "👉 https://whatsapp.hotboat.cl/booking\n\n"
                "¡Ahí podrás ver disponibilidad, fotos y reservar directamente! ⚓"
            )
        elif menu_option == 11:
            # Traer comida o pedir aquí
            _db_comida = _get_bot_response_content("comida", language)
            sequence = [p.strip() for p in _db_comida.split("\n---\n")] if _db_comida else [
                "Pueden traer lo que quieran para comer o tomar 🍕🥗",
                "o pueden pedir aquí 🙂",
            ]
            for i, msg in enumerate(sequence):
                if i > 0:
                    await asyncio.sleep(1.5)
                await _send(msg)
            conversation["last_interaction"] = datetime.now(CHILE_TZ).isoformat()
            return {"status": "success", "phone_number": phone_number,
                    "menu_option": menu_option, "message_sent": f"{len(sequence)} mensajes enviados",
                    "whatsapp_response": {}}
        elif menu_option == 12:
            # Lluvia
            _db_lluvia = _get_bot_response_content("lluvia", language)
            sequence = [p.strip() for p in _db_lluvia.split("\n---\n")] if _db_lluvia else [
                "Con lluvia la experiencia es aún mejor ☔🔥",
                "¡El HotBoat es una tina de agua caliente! La lluvia se siente increíble desde adentro 🌧️🛁",
                "Te pasamos sombreros para que no te llegue el agua en la cara todo el tiempo 🎩😄",
            ]
            for i, msg in enumerate(sequence):
                if i > 0:
                    await asyncio.sleep(1.5)
                await _send(msg)
            conversation["last_interaction"] = datetime.now(CHILE_TZ).isoformat()
            return {"status": "success", "phone_number": phone_number,
                    "menu_option": menu_option, "message_sent": f"{len(sequence)} mensajes enviados",
                    "whatsapp_response": {}}
        elif menu_option == 13:
            # Niños
            _db_ninos = _get_bot_response_content("niños", language)
            sequence = [p.strip() for p in _db_ninos.split("\n---\n")] if _db_ninos else [
                "Sí!, los niños lo pasan increíble 🎉",
                "Pagan desde los 6 años, a los menores no los consideres en el número de personas de la reserva 👍",
            ]
            for i, msg in enumerate(sequence):
                if i > 0:
                    await asyncio.sleep(1.5)
                await _send(msg)
            conversation["last_interaction"] = datetime.now(CHILE_TZ).isoformat()
            return {"status": "success", "phone_number": phone_number,
                    "menu_option": menu_option, "message_sent": f"{len(sequence)} mensajes enviados",
                    "whatsapp_response": {}}
        else:
            # Fallback: look up the response_key from bot_responses for this menu_option
            response_text = None
            try:
                with __import__('app.db.connection', fromlist=['get_connection']).get_connection() as _conn:
                    with _conn.cursor() as _cur:
                        _col = {"en": "content_en", "pt": "content_pt"}.get(language, "content_es")
                        _cur.execute(
                            f"SELECT COALESCE({_col}, content_es) FROM bot_responses "
                            "WHERE menu_option = %s AND active = TRUE LIMIT 1",
                            (menu_option,)
                        )
                        _row = _cur.fetchone()
                        if _row and _row[0]:
                            response_text = _row[0]
            except Exception as _e:
                logger.warning(f"Custom quick-reply DB lookup failed: {_e}")
            if not response_text:
                raise HTTPException(status_code=400, detail="Invalid menu option")
        
        # Split on --- separator to support multi-message responses, then send
        sequence = [p.strip() for p in response_text.split("\n---\n") if p.strip()]
        for i, msg in enumerate(sequence):
            if i > 0:
                await asyncio.sleep(1.5)
            await _send(msg)
        
        # Update last interaction
        conversation["last_interaction"] = datetime.now(CHILE_TZ).isoformat()
        
        return {
            "status": "success",
            "phone_number": phone_number,
            "menu_option": menu_option,
            "message_sent": f"{len(sequence)} mensaje(s) enviado(s)" if len(sequence) > 1 else (response_text[:100] + "..." if len(response_text) > 100 else response_text),
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending quick reply: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# PUSH NOTIFICATIONS ENDPOINTS
# ============================================================================

class PushTokenRegister(BaseModel):
    token: str  # Expo push token
    device_info: Optional[Dict] = None


class PushTokenUnregister(BaseModel):
    token: str


class PushTestNotification(BaseModel):
    title: str
    body: str


@app.post("/api/push/register")
async def register_push_token(request: PushTokenRegister):
    """Register a device for push notifications"""
    try:
        success = await push_notifier.register_push_token(
            token=request.token,
            device_info=request.device_info
        )
        
        if success:
            return {
                "status": "success",
                "message": "Push token registered successfully"
            }
        else:
            raise HTTPException(status_code=400, detail="Failed to register push token")
            
    except Exception as e:
        logger.error(f"Error registering push token: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/push/unregister")
async def unregister_push_token(request: PushTokenUnregister):
    """Unregister a device from push notifications"""
    try:
        success = await push_notifier.unregister_push_token(token=request.token)
        
        if success:
            return {
                "status": "success",
                "message": "Push token unregistered successfully"
            }
        else:
            raise HTTPException(status_code=400, detail="Failed to unregister push token")
            
    except Exception as e:
        logger.error(f"Error unregistering push token: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/push/test")
async def send_test_notification(request: PushTestNotification):
    """Send a test push notification to all registered devices"""
    try:
        success = await push_notifier.send_notification(
            title=request.title,
            body=request.body,
            priority="high"
        )
        
        if success:
            return {
                "status": "success",
                "message": "Test notification sent"
            }
        else:
            return {
                "status": "warning",
                "message": "No devices registered or notification failed"
            }
            
    except Exception as e:
        logger.error(f"Error sending test notification: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/push/status")
async def push_status(x_admin_key: str = Header(...)):
    """Return registered push tokens with diagnostic info"""
    settings = get_settings()
    if x_admin_key != settings.admin_api_key:
        raise HTTPException(status_code=403, detail="Forbidden")
    try:
        from app.db.connection import get_connection
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT token, device_info, created_at, last_used_at
                    FROM push_tokens
                    ORDER BY last_used_at DESC
                """)
                rows = cur.fetchall()
                tokens = []
                for row in rows:
                    token, device_info, created_at, last_used_at = row
                    short = token[-12:] if token else "?"
                    tokens.append({
                        "token_suffix": f"...{short}",
                        "device_info": device_info,
                        "created_at": created_at.isoformat() if created_at else None,
                        "last_used_at": last_used_at.isoformat() if last_used_at else None,
                        "active": last_used_at is not None and (
                            (datetime.now() - last_used_at.replace(tzinfo=None)).days < 90
                        )
                    })
                return {"total": len(tokens), "tokens": tokens}
    except Exception as e:
        logger.error(f"Error getting push status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/push/web-status")
async def push_web_status(x_admin_key: str = Header(...)):
    """Return registered Web Push subscriptions with diagnostic info."""
    settings = get_settings()
    if x_admin_key != settings.admin_api_key:
        raise HTTPException(status_code=403, detail="Forbidden")
    try:
        from app.db.connection import get_connection
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT endpoint, created_at, last_used_at
                    FROM web_push_subscriptions
                    ORDER BY last_used_at DESC NULLS LAST
                """)
                rows = cur.fetchall()
                subs = []
                for endpoint, created_at, last_used_at in rows:
                    short = endpoint[-30:] if endpoint else "?"
                    active = last_used_at is not None and (
                        (datetime.now() - last_used_at.replace(tzinfo=None)).days < 90
                    )
                    subs.append({
                        "endpoint_suffix": f"...{short}",
                        "created_at": created_at.isoformat() if created_at else None,
                        "last_used_at": last_used_at.isoformat() if last_used_at else None,
                        "active": active,
                    })
        return {"total": len(subs), "subscriptions": subs}
    except Exception as e:
        logger.error(f"Error getting web push status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# MESSAGE REACTIONS ENDPOINT
# ============================================================================

class MessageReaction(BaseModel):
    emoji: str
    phone_number: str


@app.post("/api/messages/{message_id}/react")
async def react_to_message(message_id: int, reaction: MessageReaction):
    """Send a reaction to a WhatsApp message"""
    try:
        logger.info(f"📨 Received reaction request: message_id={message_id}, emoji={reaction.emoji}, phone={reaction.phone_number}")
        
        from app.db.connection import get_connection
        from app.whatsapp.client import WhatsAppClient

        # Get the WhatsApp message ID from database
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT message_id, phone_number
                    FROM whatsapp_conversations
                    WHERE id = %s
                """, (message_id,))

                result = cur.fetchone()
                logger.info(f"🔍 Database query result: {result}")
                
                if not result:
                    logger.error(f"❌ Message {message_id} not found in database")
                    raise HTTPException(status_code=404, detail="Message not found")

                whatsapp_message_id = result[0]
                phone_number = result[1]
                
                logger.info(f"📱 WhatsApp message_id: {whatsapp_message_id}, phone: {phone_number}")

                if not whatsapp_message_id:
                    logger.error(f"❌ Message {message_id} has no WhatsApp message ID")
                    raise HTTPException(status_code=400, detail="Message does not have a WhatsApp message ID")

        # Send reaction via WhatsApp API
        client = WhatsAppClient()
        logger.info(f"📤 Sending reaction to WhatsApp API...")
        response = await client.send_reaction(
            to=reaction.phone_number,
            message_id=whatsapp_message_id,
            emoji=reaction.emoji
        )

        logger.info(f"✅ Reaction {reaction.emoji} sent to message {whatsapp_message_id}")

        return {
            "status": "success",
            "message_id": message_id,
            "whatsapp_message_id": whatsapp_message_id,
            "emoji": reaction.emoji,
            "whatsapp_response": response
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error sending reaction: {e}")
        logger.error(f"❌ Error type: {type(e).__name__}")
        logger.error(f"❌ Error details: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


class ConversationImport(BaseModel):
    phone_number: str
    customer_name: Optional[str] = None
    conversations: List[dict]  # List of {message, response, timestamp, direction, message_id}


@app.post("/import/conversations")
async def import_conversations(data: ConversationImport):
    """Import existing conversation history"""
    try:
        imported_count = await import_conversation_batch(
            conversations=data.conversations,
            phone_number=data.phone_number,
            customer_name=data.customer_name
        )
        
        return {
            "status": "success",
            "phone_number": data.phone_number,
            "imported": imported_count,
            "total": len(data.conversations)
        }
    except Exception as e:
        logger.error(f"Error importing conversations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Kia-Ai API Endpoints

@app.get("/api/conversations")
async def get_conversations_list(limit: int = Query(50, ge=1, le=1000)):
    """Get list of all conversations with latest messages"""
    try:
        conversations = await get_recent_conversations(limit=limit)
        return {
            "conversations": conversations,
            "total": len(conversations)
        }
    except Exception as e:
        logger.error(f"Error getting conversations: {e}")
        return {
            "conversations": [],
            "total": 0,
            "error": str(e)
        }


@app.get("/api/conversations/search")
async def search_conversations(q: str = Query(..., min_length=3)):
    """Search conversations by phone number (partial match). Finds conversations even if not in recent list."""
    try:
        results = await search_conversations_by_phone(q, limit=20)
        return {
            "conversations": results,
            "total": len(results)
        }
    except Exception as e:
        logger.error(f"Error searching conversations: {e}")
        return {
            "conversations": [],
            "total": 0,
            "error": str(e)
        }


@app.get("/api/conversations/search-messages")
async def search_messages(q: str = Query(..., min_length=2)):
    """Search for text across ALL messages in the database. Returns conversations that contain the search term."""
    import asyncio
    try:
        logger.info(f"Searching messages for: '{q}'")
        # Run blocking DB query in thread pool to avoid blocking event loop
        results = await asyncio.to_thread(search_messages_in_all_conversations_sync, q, 50)
        logger.info(f"Search found {len(results)} conversations")
        return {
            "conversations": results,
            "total": len(results)
        }
    except Exception as e:
        logger.error(f"Error searching messages: {e}", exc_info=True)
        return {
            "conversations": [],
            "total": 0,
            "error": str(e)
        }


# In-memory cache so we only call the LLM when there are new messages.
# phone_number -> {"key": <last msg timestamp>, "data": {...}}
_booking_ctx_ai_cache: Dict[str, dict] = {}


def _ai_extract_booking(history: list) -> dict:
    """Use Groq/llama to extract reservation date/time/people from customer messages.

    Only customer (incoming) messages are sent to avoid bot noise like price lists
    or 'Fecha: N/A' placeholders that confuse the model.
    """
    import json as _json
    from openai import OpenAI

    # Only incoming (customer) messages — they are the source of date/time/people
    customer_msgs = [
        m["message_text"].strip()
        for m in history
        if m.get("direction") == "incoming"
        and isinstance(m.get("message_text"), str)
        and m.get("message_text").strip()
    ]
    recent = customer_msgs[-20:]  # last 20 customer turns is more than enough
    if not recent:
        return {}

    transcript = "\n".join(f"- {t}" for t in recent)

    today = datetime.now(CHILE_TZ)
    weekdays_es = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    today_str = f"{today.strftime('%Y-%m-%d')} ({weekdays_es[today.weekday()]})"

    # Build next-weekday reference for the prompt so the model can resolve "miércoles" etc.
    next_days = {}
    for delta in range(1, 8):
        d = today + timedelta(days=delta)
        next_days[weekdays_es[d.weekday()]] = d.strftime("%Y-%m-%d")
    next_days_hint = ", ".join(f"{k} → {v}" for k, v in next_days.items())

    system = (
        "Eres un extractor de datos de reserva para una empresa de paseos en bote en Chile. "
        f"Hoy es {today_str}. "
        f"Próximos días de semana: {next_days_hint}. "
        "Lee los mensajes del CLIENTE (solo ellos) e identifica la fecha, hora y número de personas "
        "que quiere reservar. Usa SIEMPRE la mención MÁS RECIENTE. "
        "Resuelve fechas relativas con los datos de hoy: 'mañana', 'miércoles', 'jueves 25', etc. "
        "El número de personas es lo que el cliente menciona querer reservar (ej: 'somos 4', 'para 3'). "
        "Responde SOLO un objeto JSON con: "
        "date_iso (YYYY-MM-DD o null), date_display (texto corto en español ej '25 de junio' o null), "
        "time (HH:MM en 24h o null), people (entero o null). "
        "Si un dato no se menciona explícitamente, pon null."
    )

    try:
        client = OpenAI(
            api_key=settings.groq_api_key,
            base_url="https://api.groq.com/openai/v1",
        )
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": f"Mensajes del cliente:\n{transcript}"},
            ],
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=150,
        )
        data = _json.loads(resp.choices[0].message.content)
        return {
            "date_iso": data.get("date_iso") or None,
            "date_display": data.get("date_display") or None,
            "time": data.get("time") or None,
            "quantity": str(data["people"]) if data.get("people") else None,
        }
    except Exception as e:
        logger.warning(f"AI booking extraction failed: {e}")
        return {}


@app.get("/api/conversations/{phone_number}/booking-context")
async def get_booking_context(phone_number: str):
    """Return name/phone/email + reservation date/time/people for the chat admin panel."""
    import re as _re
    lead = await get_or_create_lead(phone_number)

    # Pull pending_reservation from in-memory conversation state if available
    pending: dict = {}
    if phone_number in conversation_manager.conversations:
        meta = conversation_manager.conversations[phone_number].get("metadata", {})
        pending = meta.get("pending_reservation") or {}

    history = await get_conversation_history(phone_number, limit=80)

    # Email via cheap regex (reliable)
    email = ""
    email_rx = _re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
    for msg in reversed(history):
        text = msg.get("message_text", "") or ""
        if isinstance(text, str):
            m = email_rx.search(text)
            if m:
                email = m.group(0)
                break

    # Date/time/people via AI (handles natural language), cached by last message
    last_key = history[-1].get("timestamp") if history else None
    cached = _booking_ctx_ai_cache.get(phone_number)
    if cached and cached.get("key") == last_key:
        ai_data = cached["data"]
    else:
        ai_data = await asyncio.to_thread(_ai_extract_booking, history)
        _booking_ctx_ai_cache[phone_number] = {"key": last_key, "data": ai_data}

    # Live pending_reservation takes priority; AI fills the rest
    date_display = pending.get("date") or ai_data.get("date_display")
    time_val = pending.get("time") or ai_data.get("time")
    quantity = pending.get("quantity") or ai_data.get("quantity")
    date_iso = (pending.get("date_obj_iso") or "")[:10] or ai_data.get("date_iso")

    return {
        "name": lead.get("customer_name", ""),
        "phone": phone_number,
        "email": email,
        "date_display": date_display,
        "date_iso": date_iso,
        "time": time_val,
        "quantity": quantity,
    }


@app.get("/api/conversations/{phone_number}")
async def get_conversation_detail(
    phone_number: str,
    limit: int = Query(50, ge=1, le=500),
    before: Optional[str] = None
):
    """Get full conversation history for a specific phone number with optional pagination"""
    try:
        lead = await get_or_create_lead(phone_number)
        
        before_dt = None
        if before:
            try:
                before_dt = datetime.fromisoformat(before)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid 'before' timestamp format.")
        
        messages_result = await get_conversation_history(
            phone_number,
            limit=limit,
            before=before_dt,
            return_has_more=True
        )
        
        if isinstance(messages_result, tuple):
            messages, has_more, next_cursor = messages_result
        else:
            messages = messages_result
            has_more = False
            next_cursor = None
        
        return {
            "lead": lead,
            "messages": messages,
            "total_messages": len(messages),
            "has_more": has_more,
            "next_cursor": next_cursor
        }
    except Exception as e:
        logger.error(f"Error getting conversation detail: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class TranslateRequest(BaseModel):
    text: str
    target_lang: str  # "en", "pt", "fr"


@app.post("/api/translate")
async def translate_message(request: TranslateRequest):
    """Translate text using Groq LLM."""
    lang_names = {
        "en": "English",
        "pt": "Portuguese (Brazilian)",
        "fr": "French",
        "es": "Spanish",
    }
    lang_name = lang_names.get(request.target_lang)
    if not lang_name:
        raise HTTPException(status_code=400, detail="target_lang must be en, pt, fr or es")
    translated = await asyncio.to_thread(_translate_text, request.text, request.target_lang)
    return {"translated": translated, "target_lang": request.target_lang}


class SendMessageRequest(BaseModel):
    to: str  # Phone number with country code (no +)
    message: Optional[str] = None
    type: str = "text"  # "text" or "image"
    image_url: Optional[str] = None
    caption: Optional[str] = None


@app.post("/api/send-message")
async def send_custom_message(request: SendMessageRequest):
    """Send a custom WhatsApp message through Kia-Ai"""
    try:
        # Validate inputs
        if not request.to:
            raise HTTPException(status_code=400, detail="Phone number is required")
        
        is_image = (request.type or "text").lower() == "image" or bool(request.image_url)
        
        if is_image:
            if not request.image_url:
                raise HTTPException(status_code=400, detail="image_url is required for image messages")
            if request.message and len(request.message) > 4096:
                raise HTTPException(status_code=400, detail="Caption too long (max 4096 characters)")
        else:
            if not request.message:
                raise HTTPException(status_code=400, detail="Message is required for text messages")
            if len(request.message) > 4096:
                raise HTTPException(status_code=400, detail="Message too long (max 4096 characters)")
        
        # Preload lead info (used for logging and manual handover activation)
        lead = None
        try:
            lead = await get_or_create_lead(request.to)
        except Exception as lead_error:
            logger.error(f"Error loading lead before send: {lead_error}")
            # Continue even if lead lookup fails
        
        message_id = ""
        result = {}
        message_type = "text"
        
        if is_image:
            caption = request.caption or request.message or ""
            result = await whatsapp_client.send_image_message(request.to, request.image_url, caption=caption or None)
            message_id = result.get('messages', [{}])[0].get('id', '')
            message_type = "image"
        else:
            result = await whatsapp_client.send_text_message(request.to, request.message)
            message_id = result.get('messages', [{}])[0].get('id', '')
            message_type = "text"
        
        # If this is the manual handover trigger, silence the bot for this conversation
        try:
            trigger_text = request.message or request.caption or ""
            if trigger_text and conversation_manager.is_manual_handover_trigger(trigger_text):
                await conversation_manager.activate_manual_handover(
                    phone_number=request.to,
                    contact_name=lead.get('customer_name', request.to) if lead else request.to
                )
                logger.info(f"Manual handover activated for {request.to} via custom message trigger")
        except Exception as handover_error:
            logger.warning(f"Could not activate manual handover for {request.to}: {handover_error}")
        
        # Log in database
        try:
            await save_conversation(
                phone_number=request.to,
                customer_name=lead.get('customer_name', request.to) if lead else request.to,
                message_text=(request.caption or request.message or "") if message_type == "image" else '',
                response_text=(request.image_url or request.caption or request.message or ""),
                message_type=message_type,
                message_id=message_id or None,
                direction='outgoing'
            )
        except Exception as db_error:
            logger.error(f"Error storing message in DB: {db_error}")
            # Don't fail the request if DB logging fails
        
        return {
            "status": "sent",
            "to": request.to,
            "message_id": message_id,
            "details": result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending custom message: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to send message: {str(e)}")


@app.post("/api/upload-and-send-image")
async def upload_and_send_image(
    image: UploadFile,
    to: str = Form(...),
    caption: Optional[str] = Form(None)
):
    """
    Upload an image file and send it via WhatsApp
    
    Args:
        image: Image file to upload
        to: Recipient phone number
        caption: Optional caption for the image
    """
    try:
        from PIL import Image as PILImage
        import tempfile
        
        # Validate inputs
        if not to:
            raise HTTPException(status_code=400, detail="Phone number is required")
        
        if not image:
            raise HTTPException(status_code=400, detail="Image file is required")
        
        # Validate file type
        if not image.content_type or not image.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="File must be an image")
        
        # Read file contents
        contents = await image.read()
        original_size_mb = len(contents) / (1024 * 1024)
        logger.info(f"📥 Processing image {image.filename} ({original_size_mb:.2f} MB) from {to}")
        
        # Save to temporary file for processing
        with tempfile.NamedTemporaryFile(delete=False, suffix='_original') as temp_file:
            temp_file.write(contents)
            original_path = temp_file.name
        
        # Process image with Pillow to ensure WhatsApp compatibility and compress if needed
        try:
            img = PILImage.open(original_path)
            
            logger.info(f"🎨 Original image format: {img.format}, mode: {img.mode}, size: {img.size}")
            
            # Convert to RGB if needed (removes alpha channel, converts CMYK, P3, etc.)
            if img.mode not in ('RGB', 'L'):  # L is grayscale
                logger.info(f"🔄 Converting image from {img.mode} to RGB")
                # If image has transparency, paste on white background
                if img.mode in ('RGBA', 'LA', 'PA'):
                    background = PILImage.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'P':
                        img = img.convert('RGBA')
                    background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                    img = background
                else:
                    img = img.convert('RGB')
            
            # WhatsApp has a 5MB limit, so we need to compress intelligently
            MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB in bytes
            
            # Start with reasonable dimensions
            max_dimension = 1600
            quality = 85
            
            # If the image is huge, reduce dimensions more aggressively
            if original_size_mb > 10:
                max_dimension = 1200
                quality = 75
            elif original_size_mb > 20:
                max_dimension = 1000
                quality = 70
            
            # Resize if too large
            if img.width > max_dimension or img.height > max_dimension:
                logger.info(f"📏 Resizing image from {img.size} to fit {max_dimension}x{max_dimension}")
                img.thumbnail((max_dimension, max_dimension), PILImage.Resampling.LANCZOS)
                logger.info(f"✅ Resized to {img.size}")
            
            # Try to compress until file size is acceptable
            processed_path = tempfile.NamedTemporaryFile(delete=False, suffix='.jpg').name
            attempts = 0
            max_attempts = 5
            
            while attempts < max_attempts:
                # Save with current settings
                img.save(processed_path, 'JPEG', quality=quality, optimize=True)
                file_size = os.path.getsize(processed_path)
                file_size_mb = file_size / (1024 * 1024)
                
                logger.info(f"🔄 Attempt {attempts + 1}: quality={quality}, size={file_size_mb:.2f}MB")
                
                if file_size <= MAX_FILE_SIZE:
                    logger.info(f"✅ Image compressed successfully: {file_size_mb:.2f}MB (from {original_size_mb:.2f}MB)")
                    break
                
                # If still too large, reduce quality or dimensions
                if quality > 60:
                    quality -= 10
                else:
                    # If quality is already low, reduce dimensions
                    current_max = max(img.width, img.height)
                    new_max = int(current_max * 0.8)  # Reduce by 20%
                    logger.info(f"📏 Further reducing dimensions to {new_max}x{new_max}")
                    img.thumbnail((new_max, new_max), PILImage.Resampling.LANCZOS)
                    quality = 70  # Reset quality a bit
                
                attempts += 1
            
            # Check final size
            final_size = os.path.getsize(processed_path)
            if final_size > MAX_FILE_SIZE:
                logger.warning(f"⚠️ Image still large after compression: {final_size / (1024 * 1024):.2f}MB")
                # We'll try to send it anyway, WhatsApp will reject if truly too large
            
            # Clean up original
            os.unlink(original_path)
            
            temp_path = processed_path
            
        except Exception as img_error:
            logger.error(f"❌ Error processing image: {img_error}")
            # If processing fails, try with original
            temp_path = original_path
        
        try:
            # Upload to WhatsApp (always use image/jpeg after processing)
            logger.info(f"📤 Uploading processed image to WhatsApp...")
            media_id = await whatsapp_client.upload_media(temp_path, 'image/jpeg')
            
            if not media_id:
                raise HTTPException(status_code=500, detail="Failed to upload image to WhatsApp")
            
            logger.info(f"✅ Image uploaded successfully, media_id: {media_id}")
            
            # Send image message
            result = await whatsapp_client.send_image_message(
                to=to,
                media_id=media_id,
                caption=caption
            )
            
            message_id = result.get('messages', [{}])[0].get('id', '')
            
            # Get lead info
            lead = None
            try:
                lead = await get_or_create_lead(to)
            except Exception as lead_error:
                logger.error(f"Error loading lead: {lead_error}")
            
            # Log in database
            try:
                # Save with the media URL so it can be displayed in the interface
                media_url = f"/api/media/{media_id}"
                await save_conversation(
                    phone_number=to,
                    customer_name=lead.get('customer_name', to) if lead else to,
                    message_text=caption or '',
                    response_text=media_url,
                    message_type="image",
                    message_id=message_id or None,
                    direction='outgoing'
                )
            except Exception as db_error:
                logger.error(f"Error storing message in DB: {db_error}")
            
            return {
                "status": "sent",
                "to": to,
                "message_id": message_id,
                "media_id": media_id,
                "media_url": media_url,
                "details": result
            }
            
        finally:
            # Clean up temporary file
            try:
                os.unlink(temp_path)
            except Exception:
                pass
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading and sending image: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to send image: {str(e)}")


def _convert_to_whatsapp_audio(input_path: str, output_path: str) -> bool:
    """Convert any browser audio (webm/mp4/etc) to AAC/M4A for WhatsApp delivery.
    AAC in MP4 container is universally supported by WhatsApp on all devices.
    """
    try:
        import subprocess
        import imageio_ffmpeg
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        result = subprocess.run(
            [ffmpeg_exe, "-y", "-i", input_path,
             "-c:a", "aac", "-b:a", "64k", "-ac", "1",
             "-movflags", "+faststart", output_path],
            capture_output=True, timeout=30
        )
        if result.returncode != 0:
            logger.warning(f"ffmpeg conversion stderr: {result.stderr.decode(errors='replace')}")
            return False
        return True
    except Exception as e:
        logger.warning(f"Audio conversion failed: {e}")
        return False


@app.post("/api/upload-and-send-audio")
async def upload_and_send_audio(
    audio: UploadFile,
    to: str = Form(...)
):
    """
    Upload an audio file and send it via WhatsApp
    
    Args:
        audio: Audio file to upload
        to: Recipient phone number
    """
    try:
        import tempfile
        import shutil
        
        # Validate inputs
        if not to:
            raise HTTPException(status_code=400, detail="Phone number is required")
        
        if not audio:
            raise HTTPException(status_code=400, detail="Audio file is required")
        
        # Validate file type (accept audio files)
        if not audio.content_type or not audio.content_type.startswith('audio/'):
            # Also accept webm video (often used for audio recording)
            if not (audio.content_type and 'webm' in audio.content_type):
                raise HTTPException(status_code=400, detail="File must be an audio file")
        
        # Read file contents
        contents = await audio.read()
        file_size_mb = len(contents) / (1024 * 1024)
        ct = audio.content_type or ""
        logger.info(f"📥 Processing audio {audio.filename!r} type={ct!r} ({file_size_mb:.2f} MB) → {to}")

        # Detect original format from content-type
        if "webm" in ct:
            orig_suffix = ".webm"
        elif "mp4" in ct or "m4a" in ct:
            orig_suffix = ".mp4"
        elif "mpeg" in ct or "mp3" in ct:
            orig_suffix = ".mp3"
        elif "wav" in ct:
            orig_suffix = ".wav"
        elif "amr" in ct:
            orig_suffix = ".amr"
        else:
            orig_suffix = ".bin"

        with tempfile.NamedTemporaryFile(delete=False, suffix=orig_suffix) as temp_file:
            temp_file.write(contents)
            temp_path = temp_file.name

        original_temp_path = temp_path
        upload_path = temp_path
        converted_path = None
        try:
            # Always convert to AAC/M4A — the most universally supported
            # format for WhatsApp audio across all devices and API versions.
            # AMR is kept as-is (WhatsApp native voice format, no conversion needed).
            if "amr" in ct:
                mime_type = "audio/amr"
                extension = "amr"
            else:
                converted_path = temp_path + "_wa.m4a"
                if _convert_to_whatsapp_audio(original_temp_path, converted_path):
                    upload_path = converted_path
                    mime_type = "audio/mp4"
                    extension = "m4a"
                    logger.info(f"✅ Converted {orig_suffix}→m4a/aac for WhatsApp delivery")
                else:
                    # Fallback: send original and hope WhatsApp transcodes it
                    logger.warning(f"⚠️ Conversion failed — uploading original {orig_suffix} as-is")
                    mime_type = "audio/mp4" if "mp4" in ct or "m4a" in ct else (
                        "audio/mpeg" if "mpeg" in ct or "mp3" in ct else "audio/ogg"
                    )
                    extension = orig_suffix.lstrip(".")

            # Upload to WhatsApp
            logger.info(f"📤 Uploading audio to WhatsApp (MIME: {mime_type}, size: {os.path.getsize(upload_path)} bytes)...")
            media_id = await whatsapp_client.upload_media(upload_path, mime_type)
            
            if not media_id:
                raise HTTPException(status_code=500, detail="Failed to upload audio to WhatsApp")
            
            logger.info(f"✅ Audio uploaded successfully, media_id: {media_id}")
            
            # Save audio permanently to media/audio directory
            audio_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "media", "audio")
            os.makedirs(audio_dir, exist_ok=True)
            
            timestamp = datetime.now(CHILE_TZ).strftime("%Y%m%d_%H%M%S")
            permanent_filename = f"{media_id}_{timestamp}.{extension}"
            permanent_path = os.path.join(audio_dir, permanent_filename)
            
            # Copy the temporary file to permanent location
            shutil.copy2(upload_path, permanent_path)
            logger.info(f"💾 Audio saved locally: {permanent_path}")
            
            # Send audio message
            result = await whatsapp_client.send_audio_message(
                to=to,
                media_id=media_id
            )

            # Surface any application-level errors WhatsApp may embed in a 200 response
            if "error" in result:
                err = result["error"]
                logger.error(f"❌ WhatsApp send error: code={err.get('code')} msg={err.get('message')}")
                raise HTTPException(status_code=502, detail=f"WhatsApp error: {err.get('message')}")

            message_id = result.get('messages', [{}])[0].get('id', '')
            logger.info(f"✅ WhatsApp audio queued, message_id={message_id!r}")
            
            # Get lead info
            lead = None
            try:
                lead = await get_or_create_lead(to)
            except Exception as lead_error:
                logger.error(f"Error loading lead: {lead_error}")
            
            # Log in database with media_id so it can be served from local storage
            try:
                media_url = f"/api/media/{media_id}"
                await save_conversation(
                    phone_number=to,
                    customer_name=lead.get('customer_name', to) if lead else to,
                    message_text='[Audio]',
                    response_text=media_url,
                    message_type="audio",
                    message_id=message_id or None,
                    direction='outgoing'
                )
            except Exception as db_error:
                logger.error(f"Error storing audio message in DB: {db_error}")
            
            return {
                "status": "sent",
                "to": to,
                "message_id": message_id,
                "media_id": media_id,
                "media_url": media_url,
                "details": result
            }
            
        finally:
            for path in set(filter(None, [original_temp_path, converted_path])):
                try:
                    os.unlink(path)
                except Exception:
                    pass

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading and sending audio: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to send audio: {str(e)}")


@app.get("/api/media/{media_id}")
async def proxy_media(media_id: str):
    """
    Serve media file from local storage or proxy from WhatsApp.
    Priority: Local file > Download from WhatsApp > Direct proxy
    """
    if not media_id:
        raise HTTPException(status_code=400, detail="media_id is required")
    
    try:
        from pathlib import Path
        from fastapi.responses import FileResponse
        
        # Get absolute path to media directories
        base_dir = Path(__file__).parent.parent  # Go up to project root
        media_received_dir = base_dir / "media" / "received"
        media_audio_dir = base_dir / "media" / "audio"
        
        logger.debug(f"Looking for media {media_id} in media directories")
        
        # Content type mapping
        content_type_map = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
            ".gif": "image/gif",
            ".mp4": "video/mp4",
            ".ogg": "audio/ogg",
            ".oga": "audio/ogg",
            ".mp3": "audio/mpeg",
            ".m4a": "audio/mp4",
            ".wav": "audio/wav",
            ".aac": "audio/aac",
            ".webm": "audio/webm",
        }
        
        # Try to find the file in received directory first, then audio directory
        for media_dir in [media_received_dir, media_audio_dir]:
            if media_dir.exists():
                # Look for files that start with the media_id
                for file_path in media_dir.glob(f"{media_id}_*.*"):
                    if file_path.is_file():
                        logger.info(f"✅ Serving media from local file: {file_path}")
                        
                        # Determine content type from extension
                        ext = file_path.suffix.lower()
                        content_type = content_type_map.get(ext, "application/octet-stream")
                        
                        # Log serving audio files
                        if ext in [".ogg", ".mp3", ".m4a", ".wav", ".webm"]:
                            logger.info(f"🎤 Serving audio file: {file_path.name}, type: {content_type}")
                        
                        # Return the file with headers for audio playback
                        return FileResponse(
                            path=str(file_path),
                            media_type=content_type,
                            filename=file_path.name,
                            headers={
                                "Accept-Ranges": "bytes",
                                "Cache-Control": "no-cache"
                            }
                        )
            else:
                logger.warning(f"Media directory does not exist: {media_dir}")
                # Create it
                media_dir.mkdir(parents=True, exist_ok=True)
        
        # If not found locally, try to download it from WhatsApp first
        logger.debug(f"📥 Media not found locally, attempting to download from WhatsApp: {media_id}")
        from app.utils.media_handler import get_received_media_path
        local_path = get_received_media_path(media_id)
        
        download_success = await whatsapp_client.download_media(media_id, local_path)
        if download_success and os.path.exists(local_path):
            logger.info(f"✅ Media downloaded successfully, serving from: {local_path}")
            
            # Determine content type
            ext = Path(local_path).suffix.lower()
            content_type_map = {
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
                ".webp": "image/webp",
                ".gif": "image/gif",
                ".mp4": "video/mp4",
                ".ogg": "audio/ogg",
                ".oga": "audio/ogg",
                ".mp3": "audio/mpeg",
                ".m4a": "audio/mp4",
                ".wav": "audio/wav",
                ".aac": "audio/aac",
                ".webm": "audio/webm",
            }
            content_type = content_type_map.get(ext, "application/octet-stream")
            
            # Log serving audio files
            if ext in [".ogg", ".mp3", ".m4a", ".wav", ".webm"]:
                logger.info(f"🎤 Serving downloaded audio file: {os.path.basename(local_path)}, type: {content_type}")
            
            return FileResponse(
                path=local_path,
                media_type=content_type,
                filename=os.path.basename(local_path),
                headers={
                    "Accept-Ranges": "bytes",
                    "Cache-Control": "no-cache"
                }
            )
        
        # Last resort: try to proxy directly from WhatsApp (legacy behavior)
        logger.debug(f"Attempting direct proxy from WhatsApp for media: {media_id}")
        media_url = await whatsapp_client.get_media_url(media_id)
        if not media_url:
            logger.debug(f"Media URL not available for {media_id} (likely expired)")
            raise HTTPException(status_code=404, detail="Media not found - URL unavailable")
        
        logger.info(f"Attempting to proxy from: {media_url[:100]}...")
        async with httpx.AsyncClient() as client:
            resp = await client.get(media_url, timeout=30)
            if resp.status_code != 200:
                logger.error(f"❌ Failed to fetch media {media_id}: HTTP {resp.status_code}")
                raise HTTPException(status_code=404, detail=f"Media fetch failed: HTTP {resp.status_code}")
            
            content_type = resp.headers.get("content-type", "application/octet-stream")
            logger.info(f"✅ Successfully proxied media from WhatsApp")
            return StreamingResponse(iter([resp.content]), media_type=content_type)
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error serving media {media_id}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error fetching media: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.environment == "development"
    )








