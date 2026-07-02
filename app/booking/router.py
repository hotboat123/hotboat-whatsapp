"""FastAPI router for /booking and /api/booking/*"""
import logging, os, time as _time
from typing import Any, Dict, Optional
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

# Simple in-memory cache for availability (avoids re-running 60-day scan on rapid reloads)
_avail_cache: dict = {}
_AVAIL_CACHE_TTL = 30  # seconds

from app.booking.models import CreateBookingRequest
from app.meta_pixel import apply_meta_pixel_placeholder
from app.config import get_settings
from app.booking.db import (
    create_booking, update_booking_payment,
    get_booking_by_ref, get_all_bookings, PRICES,
    generate_booking_ref,
)
from app.bot.availability import AvailabilityChecker
from app.availability.availability_config import AVAILABILITY_CONFIG
from app.booking.operator_settings import is_high_season_web_addon

logger = logging.getLogger(__name__)
router = APIRouter()
CHILE_TZ = ZoneInfo("America/Santiago")


def _booking_html() -> str:
    # Diseño nuevo (verde / "soft"). El antiguo queda en booking.html como respaldo.
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "booking-soft.html")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return apply_meta_pixel_placeholder(f.read(), get_settings().meta_pixel_id)
    return "<h1>Booking page not found</h1>"


@router.get("/booking", response_class=HTMLResponse)
async def booking_page():
    return _booking_html()


@router.get("/booking/success", response_class=HTMLResponse)
async def booking_success(
    booking_ref: str = Query(None), payment_id: str = Query(None),
    collection_id: str = Query(None), collection_status: str = Query(None)
):
    pid = payment_id or collection_id or ""
    pstatus = collection_status or "approved"
    if booking_ref and pid:
        try:
            update_booking_payment(booking_ref, pid, pid, pstatus)
            try:
                from app.booking.booking_email import try_send_booking_confirmation_after_payment
                try_send_booking_confirmation_after_payment(booking_ref)
            except Exception as em_err:
                logger.warning(f"Confirmation email after payment: {em_err}")
            # Report Purchase conversion to Meta for CTWA leads
            try:
                booking = get_booking_by_ref(booking_ref)
                if booking:
                    phone = (booking.get("customer_phone") or "").strip()
                    total = float(booking.get("total_price") or booking.get("subtotal") or 0)
                    if phone and total > 0:
                        import asyncio
                        from app.meta.conversions import fire_purchase_from_booking
                        asyncio.create_task(fire_purchase_from_booking(phone, total))
            except Exception as capi_err:
                logger.warning(f"Meta CAPI Purchase (web) failed: {capi_err}")
        except Exception as e:
            logger.error(f"Payment update error: {e}")
    return _booking_html()


@router.get("/booking/failure", response_class=HTMLResponse)
async def booking_failure(booking_ref: str = Query(None)):
    return _booking_html()


@router.get("/booking/pending", response_class=HTMLResponse)
async def booking_pending(booking_ref: str = Query(None)):
    return _booking_html()


@router.get("/api/booking/dynamic-price")
async def get_dynamic_price(
    date: str = Query(..., description="YYYY-MM-DD"),
    persons: int = Query(2, ge=1, le=8),
    time: Optional[str] = Query(None, description="HH:MM, opcional — habilita el factor por horario"),
):
    """Return dynamic price multiplier and adjusted prices for a given booking date."""
    try:
        from app.booking.operator_settings import get_dp_config, calculate_dynamic_multiplier
        from app.booking.db import PRICES
        from datetime import date as _date

        booking_date = _date.fromisoformat(date)
        today = datetime.now(CHILE_TZ).date()
        days_advance = max(0, (booking_date - today).days)
        booking_hour = None
        if time:
            try:
                booking_hour = int(str(time).split(":")[0])
            except (ValueError, IndexError):
                booking_hour = None

        # Count confirmed web bookings on that day (all_appointments is canonical)
        bookings_on_day = 0
        try:
            from app.db.connection import get_connection
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """SELECT COUNT(*) FROM all_appointments
                           WHERE source = 'hotboat_web'
                             AND fecha = %s
                             AND status NOT IN ('cancelled','rejected','solicitud')""",
                        (booking_date,),
                    )
                    bookings_on_day = cur.fetchone()[0]
        except Exception as e:
            logger.warning(f"dynamic-price: could not count bookings: {e}")

        cfg = get_dp_config()
        multiplier = calculate_dynamic_multiplier(
            booking_date, bookings_on_day, days_advance, cfg, booking_hour=booking_hour
        )

        # Round adjusted prices to nearest 1000 CLP
        adjusted: dict = {}
        for n, base in PRICES.items():
            adj = round(base * multiplier / 1000) * 1000
            adjusted[str(n)] = {"base": base, "adjusted": adj, "total": adj * n}

        # Determine which factor labels are active (for UI tooltip)
        active_factors = []
        if cfg.get("enabled"):
            for rule in sorted(cfg.get("fill_rate", []), key=lambda r: r["min_bookings"], reverse=True):
                if bookings_on_day >= rule["min_bookings"]:
                    pct = round((rule["multiplier"] - 1) * 100)
                    sign = "+" if pct >= 0 else ""
                    active_factors.append(f"Demanda del día: {sign}{pct}%")
                    break
            for rule in sorted(cfg.get("advance_booking", []), key=lambda r: r["min_days"], reverse=True):
                if days_advance >= rule["min_days"]:
                    pct = round((rule["multiplier"] - 1) * 100)
                    sign = "+" if pct >= 0 else ""
                    active_factors.append(f"Anticipación ({rule.get('label','')}): {sign}{pct}%")
                    break
            weekday = booking_date.weekday()
            wk_mult = float(cfg.get("weekday", {}).get(str(weekday), 1.0))
            if wk_mult != 1.0:
                pct = round((wk_mult - 1) * 100)
                sign = "+" if pct >= 0 else ""
                DAY_NAMES = ["Lunes","Martes","Miércoles","Jueves","Viernes","Sábado","Domingo"]
                active_factors.append(f"{DAY_NAMES[weekday]}: {sign}{pct}%")
            if booking_hour is not None:
                for rule in sorted(cfg.get("hour_of_day", []), key=lambda r: r["min_hour"], reverse=True):
                    if booking_hour >= rule["min_hour"]:
                        pct = round((rule["multiplier"] - 1) * 100)
                        sign = "+" if pct >= 0 else ""
                        active_factors.append(f"Horario ({rule.get('label','')}): {sign}{pct}%")
                        break

        return {
            "date": date,
            "dp_enabled": cfg.get("enabled", False),
            "days_advance": days_advance,
            "bookings_on_day": bookings_on_day,
            "multiplier": multiplier,
            "prices": adjusted,
            "active_factors": active_factors,
        }
    except Exception as e:
        logger.error(f"dynamic-price error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/booking/availability")
async def get_availability(days: int = Query(270, ge=1, le=270)):
    cache_key = f"avail_{days}"
    cached = _avail_cache.get(cache_key)
    if cached and (_time.time() - cached["ts"]) < _AVAIL_CACHE_TTL:
        return cached["data"]

    try:
        from app.booking.operator_settings import (
            get_vacation_days, is_urgency_mode, apply_urgency_filter,
            get_operating_hours, get_urgency_fake_slots, get_urgency_days,
            get_urgency_config, get_day_urgency_config_map,
            get_day_schedule_ghost_map,
        )
        from app.db.connection import get_connection

        checker = AvailabilityChecker()
        now = datetime.now(CHILE_TZ)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=days)
        slots = await checker.get_available_slots(start, end)

        # Load vacation days and per-day urgency overrides for the range
        vacation_dates = {
            v["date"] for v in get_vacation_days(start.date(), end.date())
        }
        global_urgency = is_urgency_mode()
        urgency_day_overrides = {
            v["date"]: v["enabled"]
            for v in get_urgency_days(start.date(), end.date())
        }

        def _day_urgency_active(dk: str) -> bool:
            """True if urgency is active for this specific date (override wins over global)."""
            if dk in urgency_day_overrides:
                return urgency_day_overrides[dk]
            return global_urgency

        # Group slots by date, skipping vacation days
        grouped: dict = {}
        for s in slots:
            dk = str(s["date"])
            if dk in vacation_dates:
                continue
            if dk not in grouped:
                grouped[dk] = []
            grouped[dk].append(s["time"])

        # Compute fake_booked_slots for grey display in urgency mode.
        # Applies per-day urgency overrides: each day is evaluated independently.
        # NOTE: availability.py already applies the urgency filter correctly using
        # ``all_appointments`` booked rows. We do NOT re-apply it here to
        # avoid double-filtering that empties valid days.
        fake_booked_by_day: dict = {}

        # Load actual bookings once for the whole range (reused for urgency
        # fake-slots, schedule ghosts, and the universal booked-grey pass).
        booked_by_day: dict = {}
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT fecha::text AS d,
                               TO_CHAR(hora, 'HH24:MI') AS t
                        FROM all_appointments
                        WHERE fecha >= %s AND fecha <= %s
                          AND hora IS NOT NULL
                          AND (
                              status IS NULL
                              OR status NOT IN ('cancelled','rejected','cancelada','solicitud')
                          )
                    """, (start.date(), end.date()))
                    for row in cur.fetchall():
                        booked_by_day.setdefault(row[0], []).append(row[1])
        except Exception as e:
            logger.warning(f"fake-slots: could not fetch booked: {e}")

        any_urgency_active = global_urgency or any(v for v in urgency_day_overrides.values())
        if any_urgency_active:
            # Global config as baseline; per-day profile overrides it when assigned
            global_cfg = get_urgency_config()
            day_urgency_cfg_map = get_day_urgency_config_map(start.date(), end.date())

            def _slot_to_min(t: str) -> int:
                h, m = map(int, t.split(":"))
                return h * 60 + m

            for dk, times in grouped.items():
                if not _day_urgency_active(dk):
                    continue  # day has urgency off — no ghost slots

                # Use urgency-mode profile assigned to this day, else global config
                day_override = day_urgency_cfg_map.get(dk)
                cfg = {**global_cfg, **day_override} if day_override else global_cfg
                gap_min = int(float(cfg.get("gap_hours", 3)) * 60)

                computed_fakes = set(get_urgency_fake_slots(config=cfg))
                booked = booked_by_day.get(dk, [])
                booked_set = set(booked)
                avail_set = set(times)

                # booked ± gap expansion (used by both modes)
                booked_expansion = set()
                for bt in booked:
                    try:
                        bh, bm = map(int, bt.split(":"))
                        b_min = bh * 60 + bm
                        for delta in (-gap_min, gap_min):
                            t_min = b_min + delta
                            if 6 * 60 <= t_min < 24 * 60:
                                booked_expansion.add(f"{t_min//60:02d}:{t_min%60:02d}")
                    except Exception:
                        pass

                if day_override and cfg.get("seed_times"):
                    seed_set = set(cfg["seed_times"])
                    ghost_times_set = set(cfg.get("ghost_times") or [])

                    if not booked:
                        # No bookings → seeds are green, everything else grey.
                        grey = {t for t in times if t not in seed_set}
                        grey |= computed_fakes  # seed±gap + ghost_times
                        fake_booked_by_day[dk] = sorted(grey, key=_slot_to_min)
                    else:
                        # With a booking at X → green = (available non-booked seeds)
                        # + (X±gap slots that are available). Everything else is grey.
                        green_from_seeds = {
                            t for t in times if t in seed_set and t not in booked_set
                        }
                        green_from_expansion = set()
                        for bt in booked:
                            try:
                                bh, bm = map(int, bt.split(":"))
                                b_min = bh * 60 + bm
                                for delta in (-gap_min, gap_min):
                                    t_min = b_min + delta
                                    if 6 * 60 <= t_min < 24 * 60:
                                        cand = f"{t_min//60:02d}:{t_min%60:02d}"
                                        if cand in avail_set:
                                            green_from_expansion.add(cand)
                            except Exception:
                                pass
                        green_set = green_from_seeds | green_from_expansion
                        # Grey = available slots not in green_set + booked + ghost_times
                        grey = {t for t in times if t not in green_set}
                        grey |= ghost_times_set
                        grey |= booked_set
                        fake_booked_by_day[dk] = sorted(grey, key=_slot_to_min)

                elif not booked:
                    # Global urgency, no bookings → seed±gap + ghost_times as grey
                    fake_booked_by_day[dk] = sorted(computed_fakes, key=_slot_to_min)
                else:
                    # Global urgency with bookings → grey = booked + expansion targets
                    # that ended up NOT available (not green), plus ghost_times
                    grey = set(booked_set)
                    grey |= computed_fakes
                    for t in booked_expansion:
                        if t not in avail_set and t not in booked_set:
                            grey.add(t)
                    fake_booked_by_day[dk] = sorted(grey, key=_slot_to_min)

        def _sg(t: str) -> int:
            h, m = map(int, t.split(":"))
            return h * 60 + m

        # Schedule-type ghost slots: independent of urgency. For each day assigned
        # a schedule profile with ghost_times, mark those as grey (non-bookable).
        try:
            schedule_ghost_map = get_day_schedule_ghost_map(start.date(), end.date())
            for dk, ghosts in schedule_ghost_map.items():
                if dk not in grouped:
                    continue
                existing = set(fake_booked_by_day.get(dk, []))
                existing |= set(ghosts)
                fake_booked_by_day[dk] = sorted(existing, key=_sg)
        except Exception as e:
            logger.warning(f"Schedule ghost-slots failed: {e}")

        # Universal booked-grey pass: on every day, show existing bookings in grey
        # (instead of hiding them) so reserved slots stay visible — including plain
        # standard days with no urgency/schedule profile assigned.
        try:
            for dk in grouped:
                booked = booked_by_day.get(dk, [])
                if not booked:
                    continue
                existing = set(fake_booked_by_day.get(dk, []))
                existing |= set(booked)
                fake_booked_by_day[dk] = sorted(existing, key=_sg)
        except Exception as e:
            logger.warning(f"Booked-grey pass failed: {e}")

        result = {
            "availability": grouped,
            "operating_hours": get_operating_hours(),
            "urgency_mode": global_urgency,
            "vacation_days": list(vacation_dates),
            "fake_booked_slots": fake_booked_by_day,
        }
        _avail_cache[cache_key] = {"data": result, "ts": _time.time()}
        return result
    except Exception as e:
        logger.error(f"Availability error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/booking/prices")
async def get_prices():
    return {"prices": PRICES, "duration_hours": 2}


@router.post("/api/booking/create")
async def create_booking_endpoint(request: CreateBookingRequest):
    try:
        n = request.num_people
        if not (2 <= n <= 7):
            raise HTTPException(status_code=400, detail="Capacidad: 2-7 personas")

        # Precio dinámico: SIEMPRE recalculado en el servidor (nunca se confía en lo
        # que haya mostrado el frontend) — mismo cálculo que /api/booking/dynamic-price,
        # así lo que ve el cliente y lo que se le cobra son consistentes.
        base_pp = PRICES.get(n, 76990)
        try:
            from datetime import date as _date
            from app.booking.operator_settings import get_dynamic_multiplier_for_booking
            _dp_mult = get_dynamic_multiplier_for_booking(
                _date.fromisoformat(request.booking_date), request.booking_time
            )
        except Exception as _dpe:
            logger.warning(f"dynamic pricing at create-booking failed, using base price: {_dpe}")
            _dp_mult = 1.0
        # Redondeo al millar más cercano — misma fórmula que ya usa el frontend
        # (Math.round(basepp*mult/1000)*1000) para que lo cobrado sea EXACTO a lo mostrado.
        price_pp = round(base_pp * _dp_mult / 1000) * 1000
        subtotal = price_pp * n
        extras_list = [e.dict() for e in request.extras]
        extras_total = sum(e["price"] * e["quantity"] for e in extras_list)
        flex_amount = int(subtotal * 0.1) if request.has_flex else 0
        cdisc = float(request.coupon_discount or 0)
        boat_cap = float(subtotal + flex_amount)
        if cdisc < 0:
            cdisc = 0
        if cdisc > boat_cap:
            cdisc = boat_cap
        ccode = (request.coupon_code or "").strip() or None
        cextra = (request.coupon_extra_benefit or "").strip() or None
        total = subtotal + extras_total + flex_amount - int(round(cdisc))
        if total < 0:
            total = 0
        data = {
            "customer_name": request.customer_name,
            "customer_phone": request.customer_phone,
            "customer_email": request.customer_email,
            "customer_birthday": request.customer_birthday,
            "customer_language": request.customer_language or "es",
            "booking_date": request.booking_date,
            "booking_time": request.booking_time,
            "num_people": n,
            "price_per_person": price_pp,
            "subtotal": subtotal,
            "extras": extras_list,
            "extras_total": extras_total,
            "has_flex": request.has_flex,
            "flex_amount": flex_amount,
            "total_price": float(total),
            "source": request.source,
            "notes": request.notes,
            "coupon_code": ccode,
            "coupon_discount": cdisc,
            "coupon_extra_benefit": cextra if ccode else None,
            "utm_source": (request.utm_source or "").strip(),
            "utm_medium": (request.utm_medium or "").strip(),
            "utm_campaign": (request.utm_campaign or "").strip(),
            "utm_content": (request.utm_content or "").strip(),
            "parametro_url": (request.parametro_url or "").strip(),
        }
        result = create_booking(data)
        booking_ref = result["booking_ref"]

        # Update leads.ad_source by phone if UTM campaign/parametro_url present
        _utm_label = data["utm_campaign"] or data["parametro_url"] or data["utm_source"]
        if _utm_label:
            try:
                with __import__("app.db.connection", fromlist=["get_connection"]).get_connection() as _conn:
                    with _conn.cursor() as _cur:
                        _cur.execute(
                            "UPDATE whatsapp_leads SET ad_source=%s, updated_at=NOW()"
                            " WHERE phone_number=%s AND (ad_source IS NULL OR ad_source='')",
                            (_utm_label[:200], request.customer_phone),
                        )
                    _conn.commit()
            except Exception as _ue:
                logger.debug("web booking leads.ad_source update: %s", _ue)

        # Fire admin_new_lead immediately; booking_created is sent by the
        # pending-payment sweep after 5 min if payment not yet confirmed.
        try:
            from app.booking.booking_email import send_email_for_trigger
            send_email_for_trigger("admin_new_lead", booking_ref)
        except Exception as _em:
            logger.warning("admin_new_lead email: %s", _em)

        # Determine amount to charge (50% deposit, support test_price override)
        if request.test_price is not None and request.test_price > 0:
            woo_monto_reserva = request.test_price
            woo_monto_extras  = 0
            logger.info(f"TEST MODE: overriding WooCommerce total to {request.test_price} CLP for {booking_ref}")
        else:
            # Charge 50% upfront as deposit via Webpay/Transbank (coupon reduces boat line only)
            boat_net = max(0, int(subtotal + flex_amount - round(cdisc)))
            woo_monto_reserva = round(boat_net * 0.5)
            woo_monto_extras = round(extras_total * 0.5)

        payment_url = None
        woo_order_id = None
        if not request.skip_payment:
            try:
                from app.payment.woocommerce import create_order as woo_create_order
                woo_order = await woo_create_order(
                    reservation_id=0,
                    booking_ref=booking_ref,
                    nombre=request.customer_name,
                    telefono=request.customer_phone,
                    email=request.customer_email,
                    monto_reserva=woo_monto_reserva,
                    monto_extras=woo_monto_extras,
                    fecha=request.booking_date,
                    num_personas=request.num_people,
                )
                payment_url  = woo_order.get("payment_url")
                woo_order_id = woo_order.get("order_id")
            except Exception as pe:
                logger.warning(f"WooCommerce skip: {pe}")
                try:
                    deposit = round(total * 0.5)
                    payment_url = await _create_mp_preference(booking_ref, request, deposit)
                except Exception as mpe:
                    logger.warning(f"MercadoPago skip: {mpe}")

            # Store WooCommerce order ID so the webhook can find this booking
            if woo_order_id:
                try:
                    from app.db.connection import get_connection as _gc
                    with _gc() as conn:
                        with conn.cursor() as cur:
                            cur.execute(
                                "UPDATE all_appointments SET payment_order_id=%s, updated_at=NOW() "
                                "WHERE source='hotboat_web' AND TRIM(source_id)=TRIM(%s)",
                                (str(woo_order_id), booking_ref),
                            )
                            if cur.rowcount == 0:
                                cur.execute(
                                    "UPDATE hotboat_appointments SET payment_order_id=%s WHERE booking_ref=%s",
                                    (str(woo_order_id), booking_ref),
                                )
                            conn.commit()
                except Exception as ue:
                    logger.warning(f"Could not save woo_order_id for {booking_ref}: {ue}")

        # NOTE: we do NOT sync to all_appointments here.
        # _sync_hotboat_to_all is called by the WooCommerce webhook once payment is confirmed.
        return {
            "booking_ref": booking_ref,
            "status": result["status"],
            "total_price": total,
            "payment_url": payment_url,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Create booking error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def _create_mp_preference(booking_ref: str, req: CreateBookingRequest, total: int) -> Optional[str]:
    import httpx
    token = os.getenv("MERCADOPAGO_ACCESS_TOKEN", "")
    if not token:
        return None
    base = os.getenv("PUBLIC_BASE_URL", "https://hotboat-app.up.railway.app")
    payload = {
        "items": [{"id": booking_ref, "quantity": 1, "currency_id": "CLP", "unit_price": total,
                   "title": f"HotBoat – Depósito 50% | {req.booking_date} {req.booking_time} {req.num_people}p"}],
        "payer": {"name": req.customer_name, "phone": {"number": req.customer_phone}},
        "back_urls": {
            "success": f"{base}/booking/success?booking_ref={booking_ref}",
            "failure": f"{base}/booking/failure?booking_ref={booking_ref}",
            "pending": f"{base}/booking/pending?booking_ref={booking_ref}",
        },
        "auto_return": "approved",
        "external_reference": booking_ref,
        "statement_descriptor": "HotBoat Chile",
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(
            "https://api.mercadopago.com/checkout/preferences",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        r.raise_for_status()
        d = r.json()
        return d.get("init_point") or d.get("sandbox_init_point")


@router.get("/api/booking/{booking_ref}")
async def get_booking(booking_ref: str):
    b = get_booking_by_ref(booking_ref)
    if not b:
        raise HTTPException(status_code=404, detail="Reserva no encontrada")
    return b


@router.get("/api/bookings/admin")
async def list_bookings(limit: int = Query(100, ge=1, le=500)):
    try:
        return {"bookings": get_all_bookings(limit)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class SolicitudRequest(BaseModel):
    customer_name: str
    customer_phone: str
    customer_email: Optional[str] = None
    dates_preference: Optional[str] = None
    people: Optional[str] = None
    notes: Optional[str] = None
    service_type: str = "general"
    title: str = "Solicitud"


@router.post("/api/booking/solicitud")
async def create_solicitud(request: SolicitudRequest):
    """Create a service request (experience, accommodation, pack) — notifies admin."""
    try:
        from app.db.connection import get_connection
        notes_full = (
            f"Servicio: {request.title}\n"
            f"Tipo: {request.service_type}\n"
            f"Fechas: {request.dates_preference or '-'}\n"
            f"Personas: {request.people or '-'}\n"
            f"Notas: {request.notes or '-'}"
        )
        with get_connection() as conn:
            with conn.cursor() as cur:
                ref = generate_booking_ref()
                cur.execute(
                    "INSERT INTO all_appointments"
                    " (source,source_id,appointment_id,fecha,hora,nombre_cliente,telefono,email,"
                    "  servicio,num_personas,ingreso_reserva,ingreso_extras,ingreso_total,"
                    "  status,observaciones,created_at,updated_at)"
                    " VALUES ('web_solicitud',%s,%s,CURRENT_DATE,'00:00'::time,%s,%s,%s,"
                    "  'Consulta','1',0,0,0,'solicitud',%s,NOW(),NOW())"
                    " RETURNING source_id",
                    (
                        ref,
                        ref,
                        request.customer_name,
                        request.customer_phone,
                        request.customer_email,
                        notes_full,
                    ),
                )
                ref = cur.fetchone()[0]
                conn.commit()
        try:
            await _notify_solicitud(request, ref)
        except Exception as ne:
            logger.warning(f"Solicitud notification failed: {ne}")
        return {"status": "ok", "booking_ref": ref}
    except Exception as e:
        logger.error(f"Error creating solicitud: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class ArmaPackPayRequest(BaseModel):
    customer_name: str
    customer_phone: str
    activities: list
    alojamiento: Optional[str] = ""
    num_people: int = 2
    dates_preference: Optional[str] = None
    notes: Optional[str] = None
    total_amount: int
    deposit_amount: int


@router.post("/api/booking/arma-pack-pay")
async def arma_pack_pay(request: ArmaPackPayRequest):
    """Create a deposit payment (50%) for a custom pack via MercadoPago."""
    from app.db.connection import get_connection
    booking_ref = generate_booking_ref()
    act_list = ", ".join(request.activities)
    notes_full = (
        f"Arma tu Pack — deposito 50%\n"
        f"Actividades: {act_list}\n"
        f"Alojamiento: {request.alojamiento or 'ninguno'}\n"
        f"Personas: {request.num_people}\n"
        f"Fechas: {request.dates_preference or '-'}\n"
        f"Total estimado: ${request.total_amount:,}\n"
        f"Deposito (50%): ${request.deposit_amount:,}\n"
        f"Notas: {request.notes or '-'}"
    )
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO all_appointments"
                    " (source,source_id,appointment_id,fecha,hora,nombre_cliente,telefono,email,"
                    "  servicio,num_personas,ingreso_reserva,ingreso_extras,ingreso_total,"
                    "  status,observaciones,created_at,updated_at)"
                    " VALUES ('web_armapack',%s,%s,CURRENT_DATE,'00:00'::time,%s,%s,NULL,"
                    "  'Arma tu Pack',%s,%s,0,%s,'pendiente',%s,NOW(),NOW())",
                    (
                        booking_ref,
                        booking_ref,
                        request.customer_name,
                        request.customer_phone,
                        str(request.num_people),
                        request.deposit_amount,
                        request.total_amount,
                        notes_full,
                    ),
                )
                conn.commit()
    except Exception as e:
        logger.error(f"arma_pack_pay DB error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    token = os.getenv("MERCADOPAGO_ACCESS_TOKEN", "")
    payment_url = None
    mp_error = None

    if not token:
        mp_error = "MERCADOPAGO_ACCESS_TOKEN not configured"
        logger.warning(f"arma_pack_pay: {mp_error} — booking_ref={booking_ref}")
    else:
        try:
            import httpx
            base = os.getenv("PUBLIC_BASE_URL", "https://hotboat-app.up.railway.app")
            # MercadoPago requires integer prices for CLP
            unit_price = int(request.deposit_amount)
            payload = {
                "items": [{
                    "id": booking_ref,
                    "title": f"HotBoat Pack – Deposito 50%",
                    "quantity": 1,
                    "currency_id": "CLP",
                    "unit_price": unit_price,
                }],
                "payer": {"name": request.customer_name, "phone": {"number": request.customer_phone}},
                "back_urls": {
                    "success": f"{base}/booking/success?booking_ref={booking_ref}",
                    "failure": f"{base}/booking/failure?booking_ref={booking_ref}",
                    "pending": f"{base}/booking/pending?booking_ref={booking_ref}",
                },
                "auto_return": "approved",
                "external_reference": booking_ref,
                "statement_descriptor": "HotBoat Chile",
            }
            logger.info(f"arma_pack_pay: creating MP preference for {booking_ref}, amount={unit_price}")
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "https://api.mercadopago.com/checkout/preferences",
                    json=payload,
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=15,
                )
                logger.info(f"arma_pack_pay: MP response status={resp.status_code}")
                if resp.status_code >= 400:
                    mp_error = f"MP API error {resp.status_code}: {resp.text[:300]}"
                    logger.error(f"arma_pack_pay: {mp_error}")
                else:
                    d = resp.json()
                    payment_url = d.get("init_point") or d.get("sandbox_init_point")
                    logger.info(f"arma_pack_pay: payment_url={payment_url}")
        except Exception as mp_e:
            mp_error = str(mp_e)
            logger.error(f"arma_pack_pay: MercadoPago exception: {mp_e}")

    return {
        "booking_ref": booking_ref,
        "payment_url": payment_url,
        "deposit_amount": request.deposit_amount,
        "mp_error": mp_error,
    }


def _sync_hotboat_to_all(booking_ref: str, data: dict, status: str):
    """Upsert a hotboat web booking into all_appointments."""
    from app.db.connection import get_connection
    from psycopg.types.json import Jsonb as PgJson
    import re
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM all_appointments WHERE source='hotboat_web' AND source_id=%s", (booking_ref,))
            existing = cur.fetchone()
            if existing:
                # Update status (and total in case it changed) instead of silently returning
                cur.execute(
                    "UPDATE all_appointments SET status=%s, updated_at=NOW() WHERE id=%s",
                    (status, existing[0])
                )
                conn.commit()
                return
            fecha = data.get("booking_date")
            hora = data.get("booking_time")
            num_p = data.get("num_people")
            cur.execute("""
                INSERT INTO all_appointments
                (source, source_id, appointment_id, fecha, hora,
                 nombre_cliente, email, telefono,
                 servicio, num_personas,
                 ingreso_reserva, ingreso_extras, ingreso_total,
                 has_flex, flex_amount,
                 costo_operativo_fijo, costo_operativo_total,
                 status, extras_json, observaciones, created_at, updated_at)
                VALUES ('hotboat_web',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,18000,18000,%s,%s,%s,NOW(),NOW())
            """, (
                booking_ref, booking_ref, fecha, hora,
                data.get("customer_name"), data.get("customer_email"), data.get("customer_phone"),
                f"HotBoat Web ({num_p}p)", str(num_p),
                float(data.get("subtotal", 0)), float(data.get("extras_total", 0)), float(data.get("total_price", 0)),
                bool(data.get("has_flex", False)), float(data.get("flex_amount", 0)),
                status, PgJson(data.get("extras") or []), data.get("notes")
            ))
            conn.commit()


def _slug_for_extra_catalog_item(name: str, idx: int) -> str:
    import re as _re

    raw = _re.sub(r"[^a-z0-9]+", "_", (name or f"extra_{idx}").lower())
    raw = _re.sub(r"_+", "_", raw).strip("_") or f"extra_{idx}"
    return raw


def _flatten_saved_extras_json(raw: Any) -> Dict[str, Any]:
    """Normalize all_appointments.extras_json toward admin flat {key: {...}} shape."""
    import json as _json

    if raw is None:
        return {}
    if isinstance(raw, str):
        try:
            raw = _json.loads(raw)
        except (_json.JSONDecodeError, TypeError):
            return {}
    if isinstance(raw, list):
        out: Dict[str, Any] = {}
        for i, e in enumerate(raw):
            if not isinstance(e, dict):
                continue
            base = _slug_for_extra_catalog_item(str(e.get("name") or ""), i)
            key = base
            n = 0
            while key in out:
                n += 1
                key = f"{base}_{n}"
            out[key] = {
                "qty": int(e.get("quantity") or 1),
                "unit_price": int(float(e.get("price") or 0)),
                "name": e.get("name"),
            }
        return out
    if not isinstance(raw, dict):
        return {}
    inner_list = raw.get("extras")
    if isinstance(inner_list, list):
        return _flatten_saved_extras_json(inner_list)
    out = {}
    for k, v in raw.items():
        if k in ("extras", "price_per_person"):
            continue
        if isinstance(v, dict):
            out[k] = dict(v)
    return out


def _extras_flat_monetary_total(flat: Dict[str, Any]) -> float:
    tot = 0.0
    for v in flat.values():
        if not isinstance(v, dict):
            continue
        qty = float(v.get("qty") or v.get("nights") or 1)
        unit = float(v.get("unit_price") or 0)
        tot += qty * unit
    return tot


def _aloj_addon_key_slug(accommodation_slug: str, accommodation_id: int) -> str:
    import re as _re

    raw = (accommodation_slug or "").strip().lower().replace("-", "_")
    raw = _re.sub(r"[^a-z0-9_]", "_", raw)
    raw = _re.sub(r"_+", "_", raw).strip("_")
    return raw or f"id_{accommodation_id}"


def _merge_hotboat_reserva_accommodation_addon(
    hotboat_ref: str,
    *,
    accommodation_id: int,
    accommodation_slug: str,
    accommodation_name: str,
    check_in,
    check_out,
    nights: int,
    price_per_night: int,
    aloj_booking_ref: str,
) -> bool:
    """Add aloj__* line into hotboat_web all_appointments extras_json + recalc totals."""
    from app.db.connection import get_connection as _gc
    from psycopg.types.json import Json

    br = (hotboat_ref or "").strip()
    if not br:
        return False
    try:
        flat_base = _flatten_saved_extras_json
        slug_part = _aloj_addon_key_slug(accommodation_slug, accommodation_id)
        aloj_key = f"aloj__{slug_part}"

        with _gc() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, extras_json, COALESCE(ingreso_reserva, 0),
                           COALESCE(has_flex, FALSE), COALESCE(flex_amount, 0),
                           COALESCE(coupon_discount, 0), COALESCE(observaciones, '')
                    FROM all_appointments
                    WHERE source = 'hotboat_web' AND TRIM(source_id) = TRIM(%s)
                    LIMIT 1
                    """,
                    (br,),
                )
                row = cur.fetchone()
                if not row:
                    logger.warning("_merge_hotboat_aloj: no all_appointments row for HB ref %s", br)
                    return False
                rid, extras_raw, ingreso_reserva, has_flex, flex_amount, coupon_disc, observaciones = row

                merged = flat_base(extras_raw)
                merged[aloj_key] = {
                    "qty": int(nights),
                    "unit_price": int(price_per_night),
                    "entry_date": check_in.isoformat(),
                    "exit_date": check_out.isoformat(),
                    "name": accommodation_name,
                }

                extras_total = _extras_flat_monetary_total(merged)
                flex_amt = float(flex_amount or 0) if has_flex else 0.0
                ig_tot = (
                    float(ingreso_reserva or 0)
                    + extras_total
                    + flex_amt
                    - float(coupon_disc or 0)
                )

                snippet = f"🏠 Alojamiento WEB · ref {aloj_booking_ref}"
                obs = (observaciones or "").strip()
                new_obs = obs
                if snippet not in obs:
                    new_obs = f"{obs}\n{snippet}".strip() if obs else snippet

                cur.execute(
                    """
                    UPDATE all_appointments
                       SET extras_json = %s,
                           ingreso_extras = %s,
                           ingreso_total = %s,
                           observaciones = %s,
                           updated_at = NOW()
                     WHERE id = %s
                    """,
                    (Json(merged), extras_total, ig_tot, new_obs, rid),
                )
                conn.commit()
                logger.info(
                    "Merged alojamiento %s into HotBoat reserva %s (extras %.0f · total %.0f)",
                    aloj_booking_ref,
                    br,
                    extras_total,
                    ig_tot,
                )
                return True
    except Exception as ex:
        logger.warning("_merge_hotboat_aloj failed for %s + %s: %s", br, aloj_booking_ref, ex)
        return False


def _merge_hotboat_reserva_experience_addon(
    hotboat_ref: str,
    *,
    experience_slug: str,
    experience_name: str,
    start_date,
    num_people: int,
    price_per_person: int,
    experience_booking_ref: str,
) -> bool:
    """Add exp__* line into hotboat_web all_appointments extras_json + recalc totals."""
    from app.db.connection import get_connection as _gc
    from psycopg.types.json import Json

    br = (hotboat_ref or "").strip()
    if not br:
        return False

    exp_slug = (experience_slug or "").strip().lower()

    try:
        flat_base = _flatten_saved_extras_json

        with _gc() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, extras_json, COALESCE(ingreso_reserva, 0),
                           COALESCE(has_flex, FALSE), COALESCE(flex_amount, 0),
                           COALESCE(coupon_discount, 0), COALESCE(observaciones, '')
                    FROM all_appointments
                    WHERE source = 'hotboat_web' AND TRIM(source_id) = TRIM(%s)
                    LIMIT 1
                    """,
                    (br,),
                )
                row = cur.fetchone()
                if not row:
                    logger.warning("_merge_hotboat_exp: no all_appointments row for HB ref %s", br)
                    return False

                rid, extras_raw, ingreso_reserva, has_flex, flex_amount, coupon_disc, observaciones = row

                merged = flat_base(extras_raw)
                ref_part = (experience_booking_ref or "").strip() or exp_slug
                exp_key = f"exp__ref__{ref_part}".replace("-", "_")
                merged[exp_key] = {
                    "qty": int(num_people),
                    "unit_price": int(price_per_person),
                    "date": start_date.isoformat(),
                    "name": experience_name,
                }

                extras_total = _extras_flat_monetary_total(merged)
                flex_amt = float(flex_amount or 0) if has_flex else 0.0
                ig_tot = (
                    float(ingreso_reserva or 0)
                    + extras_total
                    + flex_amt
                    - float(coupon_disc or 0)
                )

                snippet = f"⭐ Experiencia WEB · ref {experience_booking_ref}"
                obs = (observaciones or "").strip()
                new_obs = obs
                if snippet not in obs:
                    new_obs = f"{obs}\n{snippet}".strip() if obs else snippet

                cur.execute(
                    """
                    UPDATE all_appointments
                       SET extras_json = %s,
                           ingreso_extras = %s,
                           ingreso_total = %s,
                           observaciones = %s,
                           updated_at = NOW()
                     WHERE id = %s
                    """,
                    (Json(merged), extras_total, ig_tot, new_obs, rid),
                )
                conn.commit()
                logger.info(
                    "Merged experiencia %s into HotBoat reserva %s (extras %.0f · total %.0f)",
                    experience_booking_ref,
                    br,
                    extras_total,
                    ig_tot,
                )
                return True
    except Exception as ex:
        logger.warning("_merge_hotboat_exp failed for %s + %s: %s", br, experience_booking_ref, ex)
        return False


def _merge_hotboat_reserva_pack_addon(
    hotboat_ref: str,
    *,
    pack_slug: str,
    pack_name: str,
    start_date,
    num_people: int,
    unit_price_per_person: int,
    pack_booking_ref: str,
) -> bool:
    """Add pack as exp__* line into hotboat_web all_appointments extras_json + recalc totals."""
    from app.db.connection import get_connection as _gc
    from psycopg.types.json import Json

    br = (hotboat_ref or "").strip()
    if not br:
        return False

    pk_slug = (pack_slug or "").strip().lower()
    pk_key = f"exp__{pk_slug}" if pk_slug else f"exp__id_{pack_booking_ref}"

    try:
        flat_base = _flatten_saved_extras_json

        with _gc() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, extras_json, COALESCE(ingreso_reserva, 0),
                           COALESCE(has_flex, FALSE), COALESCE(flex_amount, 0),
                           COALESCE(coupon_discount, 0), COALESCE(observaciones, '')
                    FROM all_appointments
                    WHERE source = 'hotboat_web' AND TRIM(source_id) = TRIM(%s)
                    LIMIT 1
                    """,
                    (br,),
                )
                row = cur.fetchone()
                if not row:
                    logger.warning("_merge_hotboat_pack: no all_appointments row for HB ref %s", br)
                    return False

                rid, extras_raw, ingreso_reserva, has_flex, flex_amount, coupon_disc, observaciones = row

                merged = flat_base(extras_raw)
                merged[pk_key] = {
                    "qty": int(num_people),
                    "unit_price": int(unit_price_per_person),
                    "date": start_date.isoformat(),
                    "name": pack_name,
                }

                extras_total = _extras_flat_monetary_total(merged)
                flex_amt = float(flex_amount or 0) if has_flex else 0.0
                ig_tot = (
                    float(ingreso_reserva or 0)
                    + extras_total
                    + flex_amt
                    - float(coupon_disc or 0)
                )

                snippet = f"🎁 Pack WEB · ref {pack_booking_ref}"
                obs = (observaciones or "").strip()
                new_obs = obs
                if snippet not in obs:
                    new_obs = f"{obs}\n{snippet}".strip() if obs else snippet

                cur.execute(
                    """
                    UPDATE all_appointments
                       SET extras_json = %s,
                           ingreso_extras = %s,
                           ingreso_total = %s,
                           observaciones = %s,
                           updated_at = NOW()
                     WHERE id = %s
                    """,
                    (Json(merged), extras_total, ig_tot, new_obs, rid),
                )
                conn.commit()
                logger.info(
                    "Merged pack %s into HotBoat reserva %s (extras %.0f · total %.0f)",
                    pack_booking_ref,
                    br,
                    extras_total,
                    ig_tot,
                )
                return True
    except Exception as ex:
        logger.warning("_merge_hotboat_pack failed for %s + %s: %s", br, pack_booking_ref, ex)
        return False


async def _notify_aloj_booking(
    *,
    aloj_ref: str,
    accommodation_name: str,
    customer_name: str,
    customer_phone: str,
    check_in: str,
    check_out: str,
    nights: int,
    total: float,
    deposit: float,
    hotboat_ref: str | None = None,
    confirmed: bool = False,
):
    """Send WhatsApp notification to admin for accommodation booking events."""
    import os as _os, httpx as _httpx
    token    = _os.getenv("WHATSAPP_API_TOKEN", "")
    phone_id = _os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
    admin    = _os.getenv("ADMIN_PHONE", "56974950762")
    if not token or not phone_id:
        return

    if confirmed:
        header = f"✅ *Pago Confirmado — Alojamiento* ({aloj_ref})"
        status_line = f"💳 Depósito pagado: *${int(deposit):,}*".replace(",", ".")
    else:
        header = f"🏠 *Nueva Reserva Alojamiento* ({aloj_ref})"
        status_line = f"⏳ Pendiente de pago · Depósito: *${int(deposit):,}*".replace(",", ".")

    lines = [
        header,
        "",
        f"🏠 *Alojamiento:* {accommodation_name}",
        f"👤 *Cliente:* {customer_name}",
        f"📱 *Teléfono:* {customer_phone}",
        f"📅 *Check-in:* {check_in}  →  *Check-out:* {check_out} ({nights} noche{'s' if nights!=1 else ''})",
        f"💰 *Total:* ${int(total):,}".replace(",", "."),
        status_line,
    ]
    if hotboat_ref:
        lines.append(f"🚤 *HotBoat add-on:* {hotboat_ref}")

    msg = "\n".join(lines)
    try:
        async with _httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"https://graph.facebook.com/v17.0/{phone_id}/messages",
                headers={"Authorization": f"Bearer {token}"},
                json={"messaging_product": "whatsapp", "to": admin,
                      "type": "text", "text": {"body": msg}},
            )
    except Exception as _wa_err:
        logger.warning("WhatsApp aloj notify failed %s: %s", aloj_ref, _wa_err)


def _email_aloj_booking(
    *,
    aloj_ref: str,
    accommodation_name: str,
    customer_name: str,
    customer_phone: str,
    customer_email: str,
    check_in: str,
    check_out: str,
    nights: int,
    total: float,
    deposit: float,
    hotboat_ref: str | None = None,
    confirmed: bool = False,
):
    """Send email notification to admin for accommodation booking events."""
    from app.config import get_settings
    from app.email.resend_booking import send_booking_html

    settings = get_settings()
    resend_key = (getattr(settings, "resend_api_key", "") or "").strip()
    if not resend_key:
        logger.warning("_email_aloj_booking: no RESEND key, skipping")
        return

    from_addr = (getattr(settings, "resend_from_confirmations", "") or
                 getattr(settings, "email_from", "onboarding@resend.dev")).strip()
    notif_emails = (getattr(settings, "notification_emails", "") or "").strip()
    recipients = [e.strip() for e in notif_emails.split(",") if e.strip()]
    if not recipients:
        recipients = ["hotboatnotification@gmail.com"]

    total_fmt   = f"${int(total):,}".replace(",", ".")
    deposit_fmt = f"${int(deposit):,}".replace(",", ".")

    if confirmed:
        subject     = f"✅ Pago Confirmado — {accommodation_name} · {aloj_ref}"
        status_html = f"""
        <div style="background:#ecfdf5;padding:16px;border-radius:8px;margin:16px 0;border-left:4px solid #10b981">
          <strong style="color:#065f46">✅ Pago confirmado</strong><br>
          Depósito recibido: <strong>{deposit_fmt}</strong>
        </div>"""
    else:
        subject     = f"🏠 Nueva Reserva Alojamiento — {accommodation_name} · {aloj_ref}"
        status_html = f"""
        <div style="background:#fffbeb;padding:16px;border-radius:8px;margin:16px 0;border-left:4px solid #f59e0b">
          <strong style="color:#92400e">⏳ Pendiente de pago</strong><br>
          Depósito a cobrar: <strong>{deposit_fmt}</strong>
        </div>"""

    hotboat_row = f"<p><strong>🚤 HotBoat add-on:</strong> {hotboat_ref}</p>" if hotboat_ref else ""
    email_row   = f"<p><strong>📧 Email:</strong> {customer_email}</p>" if customer_email else ""

    html = f"""
<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto">
  <h2 style="color:#1d4ed8">{'✅ Pago Confirmado — Alojamiento' if confirmed else '🏠 Nueva Reserva de Alojamiento'}</h2>
  {status_html}
  <div style="background:#f3f4f6;padding:20px;border-radius:8px;margin:16px 0">
    <h3 style="margin-top:0">Detalles de la reserva</h3>
    <p><strong>📋 Ref:</strong> {aloj_ref}</p>
    <p><strong>🏠 Alojamiento:</strong> {accommodation_name}</p>
    <p><strong>📅 Check-in:</strong> {check_in}</p>
    <p><strong>📅 Check-out:</strong> {check_out} ({nights} noche{'s' if nights != 1 else ''})</p>
    <p><strong>💰 Total:</strong> {total_fmt}</p>
    <p><strong>👤 Cliente:</strong> {customer_name}</p>
    <p><strong>📱 Teléfono:</strong> {customer_phone}</p>
    {email_row}
    {hotboat_row}
  </div>
  <p style="color:#9ca3af;font-size:12px;margin-top:24px">
    Notificación automática desde la app de reservas HotBoat.
  </p>
</div>"""

    try:
        for recipient in recipients:
            send_booking_html(
                to=recipient,
                subject=subject,
                html=html,
                from_address=from_addr,
                api_key=resend_key,
            )
        logger.info("_email_aloj_booking sent for %s (confirmed=%s) to %s", aloj_ref, confirmed, recipients)
    except Exception as e:
        logger.warning("_email_aloj_booking send error %s: %s", aloj_ref, e)


async def _notify_solicitud(req: SolicitudRequest, ref: str):
    import os, httpx as _httpx
    token = os.getenv("WHATSAPP_API_TOKEN", "")
    phone_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
    admin = os.getenv("ADMIN_PHONE", "56974950762")
    if not token or not phone_id:
        return
    msg = (
        f"📋 *Nueva Solicitud Web* ({ref})\n\n"
        f"*Servicio:* {req.title}\n"
        f"*Cliente:* {req.customer_name}\n"
        f"*Telefono:* {req.customer_phone}\n"
        f"*Fechas:* {req.dates_preference or '-'}\n"
        f"*Personas:* {req.people or '-'}\n"
        f"*Notas:* {req.notes or '-'}"
    )
    try:
        async with _httpx.AsyncClient() as client:
            await client.post(
                f"https://graph.facebook.com/v17.0/{phone_id}/messages",
                headers={"Authorization": f"Bearer {token}"},
                json={"messaging_product": "whatsapp", "to": admin,
                      "type": "text", "text": {"body": msg}},
                timeout=10
            )
    except Exception as wa_err:
        logger.warning(f"WhatsApp notify failed for solicitud {ref}: {wa_err}")

    # For accommodation requests: send an email with WhatsApp links to contact the owner
    if (req.service_type or "").startswith("alojamiento"):
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: _email_accommodation_solicitud(req, ref)
            )
        except Exception as email_err:
            logger.warning(f"Accommodation email failed for {ref}: {email_err}")


def _email_accommodation_solicitud(req: SolicitudRequest, ref: str):
    """Send email with WhatsApp links to admin for accommodation inquiries."""
    import urllib.parse
    from app.config import get_settings
    from app.email.resend_booking import send_booking_html
    from app.db.connection import get_connection

    # Parse accommodation ID/slug from service_type ("alojamiento:ID_OR_SLUG")
    parts = (req.service_type or "").split(":", 1)
    aloj_ref = parts[1].strip() if len(parts) > 1 else ""

    aloj_name = req.title or "Alojamiento"
    owner_whatsapp = None
    owner_name = None

    if aloj_ref:
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    try:
                        aloj_id = int(aloj_ref)
                        cur.execute("SELECT name, group_name, owner_whatsapp FROM alojamientos WHERE id=%s", (aloj_id,))
                    except ValueError:
                        cur.execute("SELECT name, group_name, owner_whatsapp FROM alojamientos WHERE slug=%s", (aloj_ref,))
                    row = cur.fetchone()
                    if row:
                        aloj_name, owner_name, owner_whatsapp = row
                        if not owner_name:
                            owner_name = aloj_name
        except Exception as db_err:
            logger.warning(f"Could not look up alojamiento {aloj_ref}: {db_err}")

    def _wa_link(phone: str, message: str) -> str:
        import urllib.parse
        clean = phone.replace("+", "").replace(" ", "").replace("-", "")
        return f"https://wa.me/{clean}?text={urllib.parse.quote(message)}"

    # Pre-filled WhatsApp messages
    owner_wa_section = ""
    if owner_whatsapp and owner_whatsapp.strip():
        owner_msg = (
            f"Hola! Tengo una consulta de disponibilidad de parte de HotBoat:\n\n"
            f"🏠 *Alojamiento:* {aloj_name}\n"
            f"📅 *Fechas:* {req.dates_preference or '-'}\n"
            f"👥 *Personas:* {req.people or '-'}\n\n"
            f"¿Tienen disponibilidad para estas fechas?\n\n"
            f"Cliente: {req.customer_name} ({req.customer_phone})"
        )
        owner_link = _wa_link(owner_whatsapp, owner_msg)
        display_name = owner_name or owner_whatsapp
        owner_wa_section = f"""
        <div style="background:#ecfdf5;padding:20px;border-radius:8px;margin:16px 0">
          <h3 style="margin-top:0;color:#065f46">📞 Consultar disponibilidad con {display_name}</h3>
          <p style="margin-bottom:12px">Click para abrir WhatsApp con el mensaje pre-escrito al propietario:</p>
          <a href="{owner_link}"
             style="display:inline-block;background:#25D366;color:#fff;padding:12px 24px;
                    text-decoration:none;border-radius:6px;font-weight:bold">
            💬 Consultar con {display_name}
          </a>
        </div>"""
    else:
        owner_wa_section = """
        <div style="background:#fff3cd;padding:16px;border-radius:8px;margin:16px 0;color:#856404">
          ⚠️ No hay número de WhatsApp configurado para este alojamiento. Agrega uno en el panel de administración.
        </div>"""

    clean_client = (req.customer_phone or "").replace("+", "").replace(" ", "").replace("-", "")
    client_section = ""
    if clean_client:
        client_avail_msg = (
            f"Hola {req.customer_name}! 👋 Te escribimos de parte de *HotBoat Chile* 🚤\n\n"
            f"Revisamos disponibilidad para tu solicitud:\n\n"
            f"🏠 *Alojamiento:* {aloj_name}\n"
            f"📅 *Fechas:* {req.dates_preference or '-'}\n"
            f"👥 *Personas:* {req.people or '-'}\n\n"
            f"✅ *¡SÍ hay disponibilidad!*\n"
            f"¿Coordinamos los detalles para confirmar tu reserva? 😊"
        )
        client_link = _wa_link(clean_client, client_avail_msg)
        client_section = f"""
        <div style="background:#eff6ff;padding:20px;border-radius:8px;margin:16px 0">
          <h3 style="margin-top:0;color:#1e40af">📱 Responder al cliente</h3>
          <p style="margin-bottom:4px;font-size:.9rem">El mensaje incluye los detalles de la reserva y confirma disponibilidad.<br>
          <strong>Puedes editar el mensaje en WhatsApp antes de enviarlo</strong> — cambia la línea ✅ por ❌ si no hay disponibilidad.</p>
          <a href="{client_link}"
             style="display:inline-block;background:#25D366;color:#fff;padding:12px 24px;
                    text-decoration:none;border-radius:6px;font-weight:bold;margin-top:12px">
            💬 Responder a {req.customer_name}
          </a>
        </div>"""

    html = f"""
<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto">
  <h2 style="color:#1d4ed8">🏠 Nueva Solicitud de Alojamiento — Web</h2>
  <div style="background:#f3f4f6;padding:20px;border-radius:8px;margin:16px 0">
    <h3 style="margin-top:0">Detalles de la solicitud</h3>
    <p><strong>📋 Ref:</strong> {ref}</p>
    <p><strong>🏠 Alojamiento:</strong> {aloj_name}</p>
    <p><strong>📅 Fechas:</strong> {req.dates_preference or '-'}</p>
    <p><strong>👥 Personas:</strong> {req.people or '-'}</p>
    <p><strong>👤 Cliente:</strong> {req.customer_name}</p>
    <p><strong>📱 Teléfono:</strong> {req.customer_phone}</p>
    {f"<p><strong>📧 Email:</strong> {req.customer_email}</p>" if req.customer_email else ""}
    <p><strong>📝 Notas:</strong> {req.notes or '-'}</p>
  </div>
  {owner_wa_section}
  {client_section}
  <p style="color:#9ca3af;font-size:12px;margin-top:24px">
    Solicitud automática desde la app de reservas HotBoat.
  </p>
</div>"""

    try:
        settings = get_settings()
        resend_key = (getattr(settings, "resend_api_key", "") or "").strip()
        from_addr  = (getattr(settings, "resend_from_confirmations", "") or
                      getattr(settings, "email_from", "onboarding@resend.dev")).strip()
        notif_emails = (getattr(settings, "notification_emails", "") or "").strip()
        recipients = [e.strip() for e in notif_emails.split(",") if e.strip()]
        if not recipients:
            recipients = ["hotboatnotification@gmail.com"]

        if not resend_key:
            logger.warning("_email_accommodation_solicitud: RESEND_API_KEY not set, skipping email")
            return

        for recipient in recipients:
            send_booking_html(
                to=recipient,
                subject=f"🏠 Nueva solicitud: {aloj_name} · {req.dates_preference or 'fechas a definir'}",
                html=html,
                from_address=from_addr,
                api_key=resend_key,
            )
        logger.info(f"Accommodation solicitud email sent for {ref} to {recipients}")
    except Exception as e:
        logger.warning(f"_email_accommodation_solicitud send error: {e}")


# ── Accommodation booking ─────────────────────────────────────────────────────

class AlojBookingRequest(BaseModel):
    accommodation_id: int
    accommodation_name: str
    accommodation_slug: str
    check_in: str        # YYYY-MM-DD
    check_out: str       # YYYY-MM-DD
    num_people: int = 1
    price_per_night: int
    customer_name: str
    customer_phone: str
    customer_email: Optional[str] = None
    hotboat_booking_ref: Optional[str] = None   # existing HotBoat booking (skip_payment=True)
    hotboat_date: Optional[str] = None
    hotboat_time: Optional[str] = None
    hotboat_people: Optional[int] = None
    test_price: Optional[int] = None


@router.post("/api/booking/accommodation-create")
async def create_accommodation_booking(request: AlojBookingRequest):
    import random, string
    from datetime import date as _date
    from app.db.connection import get_connection as _gc

    check_in  = _date.fromisoformat(request.check_in)
    check_out = _date.fromisoformat(request.check_out)
    nights    = (check_out - check_in).days
    if nights < 1:
        raise HTTPException(status_code=400, detail="Mínimo 1 noche")

    slug_hs = (request.accommodation_slug or "").strip() or str(request.accommodation_id)
    high_season_aloj = is_high_season_web_addon(check_in, "alojamiento", slug_hs)

    total_aloj = request.price_per_night * nights
    is_combined_with_hotboat = bool(
        (request.hotboat_booking_ref or "").strip()
        or (request.hotboat_date and request.hotboat_time and request.hotboat_people)
    )
    # Alojamiento solo: cobrar 100%. Combinado con HotBoat: 50% del alojamiento.
    deposit_aloj = round(total_aloj * 0.5) if is_combined_with_hotboat else int(total_aloj)

    # Generate accommodation booking ref
    year    = datetime.now(CHILE_TZ).year
    suffix  = "".join(random.choices(string.ascii_uppercase + string.digits, k=5))
    aloj_ref = f"HA-{year}-{suffix}"

    # Optional HotBoat add-on
    hotboat_ref     = None
    hotboat_deposit = 0
    if request.hotboat_booking_ref:
        # HotBoat booking already created in DB (skip_payment=True); look up its total
        hotboat_ref = request.hotboat_booking_ref
        try:
            with _gc() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT ingreso_total FROM all_appointments "
                        "WHERE source='hotboat_web' AND TRIM(source_id)=TRIM(%s)",
                        (hotboat_ref,),
                    )
                    row = cur.fetchone()
                    if not row:
                        cur.execute(
                            "SELECT total_price FROM hotboat_appointments WHERE booking_ref=%s",
                            (hotboat_ref,),
                        )
                        row = cur.fetchone()
                    if row:
                        hotboat_deposit = round(float(row[0]) * 0.5)
        except Exception as le:
            logger.warning(f"Could not look up hotboat booking {hotboat_ref}: {le}")
    elif request.hotboat_date and request.hotboat_time and request.hotboat_people:
        from app.booking.db import create_booking, PRICES
        n        = int(request.hotboat_people)
        price_pp = PRICES.get(n, 76990)
        hb_sub   = price_pp * n
        hotboat_deposit = round(hb_sub * 0.5)
        hb_result = create_booking({
            "customer_name":  request.customer_name,
            "customer_phone": request.customer_phone,
            "customer_email": request.customer_email,
            "booking_date":   request.hotboat_date,
            "booking_time":   request.hotboat_time,
            "num_people":     n,
            "price_per_person": price_pp,
            "subtotal":       hb_sub,
            "extras_total":   0,
            "has_flex":       False,
            "flex_amount":    0,
            "total_price":    hb_sub,
            "source":         "web",
            "notes":          f"Combinado con alojamiento: {request.accommodation_name}",
        })
        hotboat_ref = hb_result["booking_ref"]
        try:
            from app.booking.booking_email import send_email_for_trigger
            send_email_for_trigger("admin_new_lead", hotboat_ref)
        except Exception:
            pass

    # Save accommodation booking
    with _gc() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO accommodation_bookings"
                " (booking_ref, accommodation_id, accommodation_name,"
                "  customer_name, customer_phone, customer_email,"
                "  check_in, check_out, num_people,"
                "  price_per_night, total_price, deposit_amount, hotboat_ref)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (aloj_ref, request.accommodation_id, request.accommodation_name,
                 request.customer_name, request.customer_phone, request.customer_email,
                 check_in, check_out, request.num_people,
                 request.price_per_night, total_aloj, deposit_aloj, hotboat_ref)
            )
            conn.commit()

    # Calendario de extras (admin): duplicamos fila; end_date = check_out igual que accommodation_bookings
    # (último día como salida/registro — coincide con texto de mail y WooCommerce).
    try:
        nt_parts = [f"Pago web · {aloj_ref}"]
        if hotboat_ref:
            nt_parts.append(f"HotBoat: {hotboat_ref}")
        with _gc() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO extras_bookings "
                    "(booking_ref,customer_name,customer_phone,item_type,item_slug,item_name,"
                    " start_date,end_date,num_people,total_price,deposit_paid,status,notes)"
                    " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        aloj_ref,
                        request.customer_name,
                        request.customer_phone,
                        "alojamiento",
                        slug_hs,
                        request.accommodation_name,
                        check_in,
                        check_out,
                        request.num_people,
                        total_aloj,
                        deposit_aloj,
                        "pendiente",
                        " · ".join(nt_parts),
                    ),
                )
                conn.commit()
    except Exception as ex_calendar:
        logger.warning("extras_bookings calendar row skipped for %s: %s", aloj_ref, ex_calendar)

    # Vincular alojamiento en la reserva HotBoat (extras_json + totales en all_appointments)
    if hotboat_ref:
        try:
            _merge_hotboat_reserva_accommodation_addon(
                hotboat_ref,
                accommodation_id=request.accommodation_id,
                accommodation_slug=request.accommodation_slug,
                accommodation_name=request.accommodation_name,
                check_in=check_in,
                check_out=check_out,
                nights=nights,
                price_per_night=request.price_per_night,
                aloj_booking_ref=aloj_ref,
            )
        except Exception as ex_merge:
            logger.warning("HotBoat↔aloj merge skipped for %s: %s", aloj_ref, ex_merge)

    # Build WooCommerce order
    total_deposit = deposit_aloj + hotboat_deposit
    if request.test_price and request.test_price > 0:
        total_deposit = request.test_price

    fee_lines = [
        {
            "name": f"Alojamiento: {request.accommodation_name} ({nights}n {check_in.strftime('%d/%m')} al {check_out.strftime('%d/%m')})",
            "total": str(deposit_aloj),
        }
    ]
    if hotboat_ref and hotboat_deposit:
        fee_lines.append({
            "name": f"HotBoat {request.hotboat_people}p · {request.hotboat_date} {request.hotboat_time}",
            "total": str(hotboat_deposit),
        })

    extra_meta = [{"key": "accommodation_booking_ref", "value": aloj_ref}]
    if hotboat_ref:
        extra_meta.append({"key": "hotboat_combined_ref", "value": hotboat_ref})

    payment_url = None
    if not high_season_aloj:
        try:
            from app.payment.woocommerce import create_order as woo_create_order
            woo_order = await woo_create_order(
                reservation_id=0,
                booking_ref=aloj_ref,
                nombre=request.customer_name,
                telefono=request.customer_phone,
                email=request.customer_email,
                monto_reserva=0,
                custom_fee_lines=fee_lines,
                extra_meta=extra_meta,
            )
            payment_url  = woo_order.get("payment_url")
            woo_order_id = woo_order.get("order_id")
            if woo_order_id:
                with _gc() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "UPDATE accommodation_bookings SET payment_order_id=%s WHERE booking_ref=%s",
                            (str(woo_order_id), aloj_ref)
                        )
                        # Also link the combined order to the HotBoat booking
                        if hotboat_ref:
                            cur.execute(
                                "UPDATE all_appointments SET payment_order_id=%s, updated_at=NOW() "
                                "WHERE source='hotboat_web' AND TRIM(source_id)=TRIM(%s)",
                                (str(woo_order_id), hotboat_ref),
                            )
                            if cur.rowcount == 0:
                                cur.execute(
                                    "UPDATE hotboat_appointments SET payment_order_id=%s WHERE booking_ref=%s",
                                    (str(woo_order_id), hotboat_ref),
                                )
                        conn.commit()
        except Exception as pe:
            import traceback
            logger.warning("WooCommerce accommodation skip [%s]: %r\n%s",
                           type(pe).__name__, str(pe), traceback.format_exc())
    else:
        with _gc() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE accommodation_bookings SET deposit_amount=0 WHERE booking_ref=%s",
                    (aloj_ref,),
                )
                cur.execute(
                    "UPDATE extras_bookings SET deposit_paid=0, status='pendiente' "
                    "WHERE booking_ref=%s AND item_type='alojamiento'",
                    (aloj_ref,),
                )
                conn.commit()

    deposit_for_notify = 0 if high_season_aloj else deposit_aloj
    logger.info(
        "accommodation-create: %s nights=%d aloj_deposit=%d hotboat_deposit=%d high_season=%s",
        aloj_ref, nights, deposit_for_notify, hotboat_deposit, high_season_aloj,
    )

    # Notify admin via WhatsApp
    try:
        await _notify_aloj_booking(
            aloj_ref=aloj_ref,
            accommodation_name=request.accommodation_name,
            customer_name=request.customer_name,
            customer_phone=request.customer_phone,
            check_in=check_in.strftime("%d/%m/%Y"),
            check_out=check_out.strftime("%d/%m/%Y"),
            nights=nights,
            total=total_aloj,
            deposit=deposit_for_notify,
            hotboat_ref=hotboat_ref,
            confirmed=False,
        )
    except Exception as _ne:
        logger.warning("aloj notify error: %s", _ne)

    # Notify admin via email
    try:
        import threading
        threading.Thread(
            target=_email_aloj_booking,
            kwargs=dict(
                aloj_ref=aloj_ref,
                accommodation_name=request.accommodation_name,
                customer_name=request.customer_name,
                customer_phone=request.customer_phone,
                customer_email=request.customer_email or "",
                check_in=check_in.strftime("%d/%m/%Y"),
                check_out=check_out.strftime("%d/%m/%Y"),
                nights=nights,
                total=total_aloj,
                deposit=deposit_for_notify,
                hotboat_ref=hotboat_ref,
                confirmed=False,
            ),
            daemon=True,
        ).start()
    except Exception as _ee:
        logger.warning("aloj email notify error: %s", _ee)

    out: dict = {"booking_ref": aloj_ref, "total_price": total_aloj, "payment_url": payment_url}
    if high_season_aloj:
        out["requires_email"] = True
    return out


class ExperienceBookingRequest(BaseModel):
    experience_slug: str
    experience_name: str
    start_date: str  # YYYY-MM-DD
    end_date: Optional[str] = None  # YYYY-MM-DD (optional)
    num_people: int = 1
    price_per_person: int
    customer_name: str
    customer_phone: str
    customer_email: Optional[str] = None
    hotboat_booking_ref: Optional[str] = None
    notes: Optional[str] = None


class AddonCartItem(BaseModel):
    """One line in the HotBoat web cart: experience and/or pack addon."""
    item_type: str = "experience"  # "experience" | "pack"
    start_date: str
    end_date: Optional[str] = None
    num_people: int = 1
    notes: Optional[str] = None
    experience_slug: Optional[str] = None
    experience_name: Optional[str] = None
    price_per_person: Optional[int] = None
    pack_slug: Optional[str] = None
    pack_name: Optional[str] = None
    unit_price_per_person: Optional[int] = None


class ExperienceCartRequest(BaseModel):
    items: list[AddonCartItem]
    customer_name: str
    customer_phone: str
    customer_email: Optional[str] = None
    hotboat_booking_ref: Optional[str] = None


class PackBookingRequest(BaseModel):
    pack_slug: str
    pack_name: str
    start_date: str  # YYYY-MM-DD
    end_date: Optional[str] = None  # YYYY-MM-DD (optional)
    num_people: int = 1
    # Used for accounting + exp__ merging in all_appointments
    unit_price_per_person: int
    customer_name: str
    customer_phone: str
    customer_email: Optional[str] = None
    hotboat_booking_ref: Optional[str] = None
    notes: Optional[str] = None


def _gen_extras_booking_ref(prefix: str) -> str:
    year = datetime.now(CHILE_TZ).year
    import random, string

    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=5))
    return f"{prefix}-{year}-{suffix}"


def _date_fromiso(d: Optional[str]):
    from datetime import date as _date

    if not d:
        return None
    return _date.fromisoformat(d)


@router.post("/api/booking/experience-create")
async def create_experience_booking(request: ExperienceBookingRequest):
    start_d = _date_fromiso(request.start_date)
    end_d = _date_fromiso(request.end_date) if request.end_date else None
    if not start_d:
        raise HTTPException(status_code=400, detail="start_date inválida")
    if end_d and end_d < start_d:
        raise HTTPException(status_code=400, detail="end_date no puede ser anterior a start_date")

    days_count = 1
    if end_d and end_d > start_d:
        days_count = (end_d - start_d).days + 1
    if end_d and end_d == start_d:
        end_d = None

    total_price = int(request.price_per_person) * int(request.num_people) * int(days_count)
    hotboat_ref = (request.hotboat_booking_ref or "").strip()
    # Experiencia sola: cobrar 100%. Combinada con HotBoat: 50%.
    deposit_paid = round(total_price * 0.5) if hotboat_ref else int(total_price)
    exp_ref = _gen_extras_booking_ref("EX")

    # Insert calendar row first so it exists even if payment fails
    from app.db.connection import get_connection as _gc

    with _gc() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO extras_bookings "
                "(booking_ref,customer_name,customer_phone,item_type,item_slug,item_name,"
                " start_date,end_date,num_people,total_price,deposit_paid,status,notes)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    exp_ref,
                    request.customer_name,
                    request.customer_phone,
                    "experience",
                    request.experience_slug,
                    request.experience_name,
                    start_d,
                    end_d,
                    request.num_people,
                    total_price,
                    deposit_paid,
                    "pendiente",
                    (request.notes or "").strip() or f"Pago web · {exp_ref}",
                ),
            )
            conn.commit()

    # Notify admin (WhatsApp) - similar to /api/booking/solicitud
    try:
        solicitud_req = SolicitudRequest(
            customer_name=request.customer_name,
            customer_phone=request.customer_phone,
            customer_email=request.customer_email,
            dates_preference=str(start_d) + (f" al {end_d}" if end_d else ""),
            people=str(request.num_people),
            notes=(request.notes or "").strip(),
            service_type=f"experience:{request.experience_slug}",
            title=request.experience_name,
        )
        await _notify_solicitud(solicitud_req, exp_ref)
    except Exception as _notify_err:
        logger.warning("experience-create notify failed for %s: %s", exp_ref, _notify_err)

    # High season: no online payment, coordinate manually
    if is_high_season_web_addon(start_d, "experience", request.experience_slug):
        with _gc() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE extras_bookings SET status='pendiente', deposit_paid=0 WHERE booking_ref=%s AND item_type=%s",
                    (exp_ref, "experience"),
                )
                conn.commit()
        return {"booking_ref": exp_ref, "total_price": total_price, "payment_url": None, "requires_email": True}

    # If combined with HotBoat, compute hotboat deposit before merging extras into totals.
    hotboat_deposit = 0
    hotboat_label = ""
    if hotboat_ref:
        with _gc() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT ingreso_total, fecha, hora, num_personas "
                    "FROM all_appointments "
                    "WHERE source='hotboat_web' AND TRIM(source_id)=TRIM(%s) LIMIT 1",
                    (hotboat_ref,),
                )
                row = cur.fetchone()
                if row:
                    hb_total, hb_fecha, hb_hora, hb_np = row
                    hotboat_deposit = round(float(hb_total or 0) * 0.5)
                    hb_hhmm = str(hb_hora or "")[:5]
                    hotboat_label = f"HotBoat {hb_np}p · {hb_fecha} {hb_hhmm}".strip()
                else:
                    # Combined flow can exist before all_appointments row is synced.
                    cur.execute(
                        "SELECT total_price FROM hotboat_appointments WHERE booking_ref=%s",
                        (hotboat_ref,),
                    )
                    row2 = cur.fetchone()
                    if row2:
                        hotboat_deposit = round(float(row2[0] or 0) * 0.5)
                        hotboat_label = "HotBoat · deposito 50%"

    if hotboat_ref:
        try:
            _merge_hotboat_reserva_experience_addon(
                hotboat_ref,
                experience_slug=request.experience_slug,
                experience_name=request.experience_name,
                start_date=start_d,
                num_people=request.num_people,
                price_per_person=request.price_per_person,
                experience_booking_ref=exp_ref,
            )
        except Exception as ex_merge:
            logger.warning("experience-create merge failed for %s + %s: %s", hotboat_ref, exp_ref, ex_merge)

    fee_lines = [
        {
            "name": f"Experiencia: {request.experience_name} ({start_d}{f' al {end_d}' if end_d else ''})",
            "total": str(deposit_paid),
        }
    ]
    if hotboat_ref and hotboat_deposit:
        fee_lines.append({"name": hotboat_label or "HotBoat · deposito 50%", "total": str(hotboat_deposit)})

    payment_url = None
    try:
        from app.payment.woocommerce import create_order as woo_create_order

        woo_order = await woo_create_order(
            reservation_id=0,
            booking_ref=exp_ref,
            nombre=request.customer_name,
            telefono=request.customer_phone,
            email=request.customer_email,
            monto_reserva=0,
            monto_extras=0,
            fecha=str(start_d),
            num_personas=request.num_people,
            custom_fee_lines=fee_lines,
            extra_meta=[
                {"key": "hotboat_booking_ref", "value": hotboat_ref},
                {"key": "experience_booking_ref", "value": exp_ref},
            ]
            if hotboat_ref
            else [
                {"key": "experience_booking_ref", "value": exp_ref},
            ],
        )
        payment_url = woo_order.get("payment_url")
    except Exception as pe:
        logger.warning("WooCommerce experience skip [%s]: %r", exp_ref, pe)

    return {
        "booking_ref": exp_ref,
        "total_price": total_price,
        "pay_now_amount": deposit_paid,
        "payment_url": payment_url,
    }


@router.post("/api/booking/experience-cart-create")
async def create_experience_cart_booking(request: ExperienceCartRequest):
    """Create multiple extras_bookings rows (experiences and/or packs) + WooCommerce + HB merge per line."""
    if not request.items:
        raise HTTPException(status_code=400, detail="El carrito está vacío")

    from app.db.connection import get_connection as _gc

    hotboat_ref = (request.hotboat_booking_ref or "").strip()
    booking_refs: list[str] = []
    booking_db_types: list[str] = []
    fee_lines: list[dict] = []
    total_sum = 0
    pay_now_sum = 0
    any_high_season = False

    for it in request.items:
        start_d = _date_fromiso(it.start_date)
        end_d = _date_fromiso(it.end_date) if it.end_date else None
        kind = (it.item_type or "experience").strip().lower()
        label = (it.experience_name or it.pack_name or "ítem").strip()
        if not start_d:
            raise HTTPException(status_code=400, detail=f"start_date inválida ({label})")
        if end_d and end_d < start_d:
            raise HTTPException(status_code=400, detail=f"end_date inválida ({label})")

        days_count = 1
        if end_d and end_d > start_d:
            days_count = (end_d - start_d).days + 1
        if end_d and end_d == start_d:
            end_d = None

        if kind == "pack":
            if not it.pack_slug or not it.pack_name or it.unit_price_per_person is None:
                raise HTTPException(status_code=400, detail="Pack incompleto en carrito")
            total_price = int(it.unit_price_per_person) * int(it.num_people) * int(days_count)
            deposit_paid = round(total_price * 0.5) if hotboat_ref else int(total_price)
            row_ref = _gen_extras_booking_ref("PK")
            db_item_type = "pack"

            with _gc() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO extras_bookings "
                        "(booking_ref,customer_name,customer_phone,item_type,item_slug,item_name,"
                        " start_date,end_date,num_people,total_price,deposit_paid,status,notes)"
                        " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (
                            row_ref,
                            request.customer_name,
                            request.customer_phone,
                            db_item_type,
                            it.pack_slug,
                            it.pack_name,
                            start_d,
                            end_d,
                            it.num_people,
                            total_price,
                            deposit_paid,
                            "pendiente",
                            (it.notes or "").strip() or f"Pago web carrito · {row_ref}",
                        ),
                    )
                    conn.commit()

            try:
                solicitud_req = SolicitudRequest(
                    customer_name=request.customer_name,
                    customer_phone=request.customer_phone,
                    customer_email=request.customer_email,
                    dates_preference=str(start_d) + (f" al {end_d}" if end_d else ""),
                    people=str(it.num_people),
                    notes=(it.notes or "").strip(),
                    service_type=f"pack:{it.pack_slug}",
                    title=it.pack_name,
                )
                await _notify_solicitud(solicitud_req, row_ref)
            except Exception as _notify_err:
                logger.warning("addon-cart pack notify failed for %s: %s", row_ref, _notify_err)

            if is_high_season_web_addon(start_d, "pack", it.pack_slug):
                any_high_season = True
                with _gc() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "UPDATE extras_bookings SET status='pendiente', deposit_paid=0 "
                            "WHERE booking_ref=%s AND item_type=%s",
                            (row_ref, "pack"),
                        )
                        conn.commit()
            else:
                fee_lines.append(
                    {
                        "name": f"Pack: {it.pack_name} ({start_d}{f' al {end_d}' if end_d else ''})",
                        "total": str(deposit_paid),
                    }
                )

            total_sum += total_price
            pay_now_sum += deposit_paid
            booking_refs.append(row_ref)
            booking_db_types.append(db_item_type)

            if hotboat_ref:
                try:
                    _merge_hotboat_reserva_pack_addon(
                        hotboat_ref,
                        pack_slug=it.pack_slug,
                        pack_name=it.pack_name,
                        start_date=start_d,
                        num_people=it.num_people,
                        unit_price_per_person=it.unit_price_per_person,
                        pack_booking_ref=row_ref,
                    )
                except Exception as ex_merge:
                    logger.warning("addon-cart pack merge failed %s + %s: %s", hotboat_ref, row_ref, ex_merge)

            continue

        # --- experience line ---
        if not it.experience_slug or not it.experience_name or it.price_per_person is None:
            raise HTTPException(status_code=400, detail="Experiencia incompleta en carrito")

        total_price = int(it.price_per_person) * int(it.num_people) * int(days_count)
        deposit_paid = round(total_price * 0.5) if hotboat_ref else int(total_price)
        exp_ref = _gen_extras_booking_ref("EX")

        with _gc() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO extras_bookings "
                    "(booking_ref,customer_name,customer_phone,item_type,item_slug,item_name,"
                    " start_date,end_date,num_people,total_price,deposit_paid,status,notes)"
                    " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        exp_ref,
                        request.customer_name,
                        request.customer_phone,
                        "experience",
                        it.experience_slug,
                        it.experience_name,
                        start_d,
                        end_d,
                        it.num_people,
                        total_price,
                        deposit_paid,
                        "pendiente",
                        (it.notes or "").strip() or f"Pago web carrito · {exp_ref}",
                    ),
                )
                conn.commit()

        try:
            solicitud_req = SolicitudRequest(
                customer_name=request.customer_name,
                customer_phone=request.customer_phone,
                customer_email=request.customer_email,
                dates_preference=str(start_d) + (f" al {end_d}" if end_d else ""),
                people=str(it.num_people),
                notes=(it.notes or "").strip(),
                service_type=f"experience:{it.experience_slug}",
                title=it.experience_name,
            )
            await _notify_solicitud(solicitud_req, exp_ref)
        except Exception as _notify_err:
            logger.warning("experience-cart notify failed for %s: %s", exp_ref, _notify_err)

        if is_high_season_web_addon(start_d, "experience", it.experience_slug):
            any_high_season = True
            with _gc() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE extras_bookings SET status='pendiente', deposit_paid=0 "
                        "WHERE booking_ref=%s AND item_type=%s",
                        (exp_ref, "experience"),
                    )
                    conn.commit()
        else:
            fee_lines.append(
                {
                    "name": f"Experiencia: {it.experience_name} ({start_d}{f' al {end_d}' if end_d else ''})",
                    "total": str(deposit_paid),
                }
            )

        total_sum += total_price
        pay_now_sum += deposit_paid
        booking_refs.append(exp_ref)
        booking_db_types.append("experience")

        if hotboat_ref:
            try:
                _merge_hotboat_reserva_experience_addon(
                    hotboat_ref,
                    experience_slug=it.experience_slug,
                    experience_name=it.experience_name,
                    start_date=start_d,
                    num_people=it.num_people,
                    price_per_person=it.price_per_person,
                    experience_booking_ref=exp_ref,
                )
            except Exception as ex_merge:
                logger.warning("experience-cart merge failed %s + %s: %s", hotboat_ref, exp_ref, ex_merge)

    if any_high_season:
        fee_lines.clear()
        with _gc() as conn:
            with conn.cursor() as cur:
                for ref, db_t in zip(booking_refs, booking_db_types):
                    cur.execute(
                        "UPDATE extras_bookings SET status='pendiente', deposit_paid=0 "
                        "WHERE booking_ref=%s AND item_type=%s",
                        (ref, db_t),
                    )
                conn.commit()
        return {
            "booking_refs": booking_refs,
            "primary_ref": booking_refs[0] if booking_refs else "",
            "total_price": total_sum,
            "pay_now_amount": 0,
            "payment_url": None,
            "requires_email": True,
        }

    hotboat_deposit = 0
    hotboat_label = ""
    if hotboat_ref:
        with _gc() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT ingreso_total, fecha, hora, num_personas "
                    "FROM all_appointments "
                    "WHERE source='hotboat_web' AND TRIM(source_id)=TRIM(%s) LIMIT 1",
                    (hotboat_ref,),
                )
                row = cur.fetchone()
                if row:
                    hb_total, hb_fecha, hb_hora, hb_np = row
                    hotboat_deposit = round(float(hb_total or 0) * 0.5)
                    hb_hhmm = str(hb_hora or "")[:5]
                    hotboat_label = f"HotBoat {hb_np}p · {hb_fecha} {hb_hhmm}".strip()
                else:
                    cur.execute(
                        "SELECT total_price FROM hotboat_appointments WHERE booking_ref=%s",
                        (hotboat_ref,),
                    )
                    row2 = cur.fetchone()
                    if row2:
                        hotboat_deposit = round(float(row2[0] or 0) * 0.5)
                        hotboat_label = "HotBoat · deposito 50%"

    if hotboat_ref and hotboat_deposit:
        fee_lines.append({"name": hotboat_label or "HotBoat · deposito 50%", "total": str(hotboat_deposit)})

    payment_url = None
    if fee_lines:
        try:
            from app.payment.woocommerce import create_order as woo_create_order

            meta = [{"key": "experience_cart_refs", "value": ",".join(booking_refs)}]
            if hotboat_ref:
                meta.append({"key": "hotboat_booking_ref", "value": hotboat_ref})

            first_start = _date_fromiso(request.items[0].start_date)
            woo_order = await woo_create_order(
                reservation_id=0,
                booking_ref=booking_refs[0],
                nombre=request.customer_name,
                telefono=request.customer_phone,
                email=request.customer_email,
                monto_reserva=0,
                monto_extras=0,
                fecha=str(first_start) if first_start else None,
                num_personas=request.items[0].num_people,
                custom_fee_lines=fee_lines,
                extra_meta=meta,
            )
            payment_url = woo_order.get("payment_url")
        except Exception as pe:
            logger.warning("WooCommerce experience-cart skip [%s]: %r", booking_refs, pe)

    return {
        "booking_refs": booking_refs,
        "primary_ref": booking_refs[0] if booking_refs else "",
        "total_price": total_sum,
        "pay_now_amount": pay_now_sum,
        "payment_url": payment_url,
    }


@router.post("/api/booking/pack-create")
async def create_pack_booking(request: PackBookingRequest):
    start_d = _date_fromiso(request.start_date)
    end_d = _date_fromiso(request.end_date) if request.end_date else None
    if not start_d:
        raise HTTPException(status_code=400, detail="start_date inválida")
    if end_d and end_d < start_d:
        raise HTTPException(status_code=400, detail="end_date no puede ser anterior a start_date")

    days_count = 1
    if end_d and end_d > start_d:
        days_count = (end_d - start_d).days + 1
    if end_d and end_d == start_d:
        end_d = None

    total_price = int(request.unit_price_per_person) * int(request.num_people) * int(days_count)
    deposit_paid = round(total_price * 0.5)
    pack_ref = _gen_extras_booking_ref("PK")

    from app.db.connection import get_connection as _gc

    with _gc() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO extras_bookings "
                "(booking_ref,customer_name,customer_phone,item_type,item_slug,item_name,"
                " start_date,end_date,num_people,total_price,deposit_paid,status,notes)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    pack_ref,
                    request.customer_name,
                    request.customer_phone,
                    "pack",
                    request.pack_slug,
                    request.pack_name,
                    start_d,
                    end_d,
                    request.num_people,
                    total_price,
                    deposit_paid,
                    "pendiente",
                    (request.notes or "").strip() or f"Pago web · {pack_ref}",
                ),
            )
            conn.commit()

    # Notify admin (WhatsApp) - similar to /api/booking/solicitud
    try:
        solicitud_req = SolicitudRequest(
            customer_name=request.customer_name,
            customer_phone=request.customer_phone,
            customer_email=request.customer_email,
            dates_preference=str(start_d) + (f" al {end_d}" if end_d else ""),
            people=str(request.num_people),
            notes=(request.notes or "").strip(),
            service_type=f"pack:{request.pack_slug}",
            title=request.pack_name,
        )
        await _notify_solicitud(solicitud_req, pack_ref)
    except Exception as _notify_err:
        logger.warning("pack-create notify failed for %s: %s", pack_ref, _notify_err)

    hotboat_ref = (request.hotboat_booking_ref or "").strip()

    if is_high_season_web_addon(start_d, "pack", request.pack_slug):
        with _gc() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE extras_bookings SET status='pendiente', deposit_paid=0 WHERE booking_ref=%s AND item_type=%s",
                    (pack_ref, "pack"),
                )
                conn.commit()
        return {"booking_ref": pack_ref, "total_price": total_price, "payment_url": None, "requires_email": True}

    hotboat_deposit = 0
    hotboat_label = ""
    if hotboat_ref:
        with _gc() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT ingreso_total, fecha, hora, num_personas "
                    "FROM all_appointments "
                    "WHERE source='hotboat_web' AND TRIM(source_id)=TRIM(%s) LIMIT 1",
                    (hotboat_ref,),
                )
                row = cur.fetchone()
                if row:
                    hb_total, hb_fecha, hb_hora, hb_np = row
                    hotboat_deposit = round(float(hb_total or 0) * 0.5)
                    hb_hhmm = str(hb_hora or "")[:5]
                    hotboat_label = f"HotBoat {hb_np}p · {hb_fecha} {hb_hhmm}".strip()
                else:
                    # Combined flow can exist before all_appointments row is synced.
                    cur.execute(
                        "SELECT total_price FROM hotboat_appointments WHERE booking_ref=%s",
                        (hotboat_ref,),
                    )
                    row2 = cur.fetchone()
                    if row2:
                        hotboat_deposit = round(float(row2[0] or 0) * 0.5)
                        hotboat_label = "HotBoat · deposito 50%"

    if hotboat_ref:
        try:
            _merge_hotboat_reserva_pack_addon(
                hotboat_ref,
                pack_slug=request.pack_slug,
                pack_name=request.pack_name,
                start_date=start_d,
                num_people=request.num_people,
                unit_price_per_person=request.unit_price_per_person,
                pack_booking_ref=pack_ref,
            )
        except Exception as ex_merge:
            logger.warning("pack-create merge failed for %s + %s: %s", hotboat_ref, pack_ref, ex_merge)

    fee_lines = [
        {
            "name": f"Pack: {request.pack_name} ({start_d}{f' al {end_d}' if end_d else ''})",
            "total": str(deposit_paid),
        }
    ]
    if hotboat_ref and hotboat_deposit:
        fee_lines.append({"name": hotboat_label or "HotBoat · deposito 50%", "total": str(hotboat_deposit)})

    payment_url = None
    try:
        from app.payment.woocommerce import create_order as woo_create_order

        woo_order = await woo_create_order(
            reservation_id=0,
            booking_ref=pack_ref,
            nombre=request.customer_name,
            telefono=request.customer_phone,
            email=request.customer_email,
            monto_reserva=0,
            monto_extras=0,
            fecha=str(start_d),
            num_personas=request.num_people,
            custom_fee_lines=fee_lines,
            extra_meta=[
                {"key": "hotboat_booking_ref", "value": hotboat_ref},
                {"key": "pack_booking_ref", "value": pack_ref},
            ]
            if hotboat_ref
            else [
                {"key": "pack_booking_ref", "value": pack_ref},
            ],
        )
        payment_url = woo_order.get("payment_url")
    except Exception as pe:
        logger.warning("WooCommerce pack skip [%s]: %r", pack_ref, pe)

    return {"booking_ref": pack_ref, "total_price": total_price, "payment_url": payment_url}


# ── Booking page visitor tracking ─────────────────────────────────────────────

# In-memory session store: session_id → {events, start_time, ...}
_visitor_sessions: dict = {}
_visitor_tasks: dict = {}  # session_id → asyncio.Task


class TrackEventRequest(BaseModel):
    event: str
    date: Optional[str] = None
    lang: Optional[str] = "es"
    referrer: Optional[str] = ""
    session_id: Optional[str] = ""
    is_returning: Optional[bool] = False
    utm_source: Optional[str] = ""
    utm_medium: Optional[str] = ""
    utm_campaign: Optional[str] = ""
    utm_content: Optional[str] = ""
    fbclid: Optional[str] = ""  # present = clicked a Meta ad
    # Custom ad URL parameter (landing pages / Meta website URL fields)
    parametro_url: Optional[str] = ""


def _merge_visitor_session_attribution(dst: dict, body: TrackEventRequest) -> None:
    """Fill empty attribution slots (handles out-of-order / exit-only beacons after slow first request)."""
    lim = {
        "utm_source": 100,
        "utm_medium": 100,
        "utm_campaign": 200,
        "utm_content": 200,
        "parametro_url": 240,
        "referrer": 200,
    }
    pairs = [
        ("utm_source", (body.utm_source or "").strip()),
        ("utm_medium", (body.utm_medium or "").strip()),
        ("utm_campaign", (body.utm_campaign or "").strip()),
        ("utm_content", (body.utm_content or "").strip()),
        ("parametro_url", (body.parametro_url or "").strip()),
        ("referrer", (body.referrer or "").strip()),
    ]
    for key, val in pairs:
        if not val:
            continue
        cap = lim.get(key, 200)
        if not (dst.get(key) or "").strip():
            dst[key] = val[:cap]

    fb = str(body.fbclid or "").strip()
    if fb:
        dst["fbclid"] = True


@router.post("/api/booking/track")
async def track_booking_event(body: TrackEventRequest):
    """
    Collects visitor events per session, then after 5 min of inactivity
    sends a single summary email with activity timeline and classification.
    Events are persisted to the DB for analytics on every tracked call (when session_id exists).
    """
    import asyncio
    from app.booking.operator_settings import get_setting

    sid = (body.session_id or "").strip()[:64]
    if not sid:
        return {"ok": True, "sent": False}

    now_cl = datetime.now(CHILE_TZ)

    try:
        from app.booking.visitor_tracking import persist_booking_visitor_event

        persist_booking_visitor_event(
            sid,
            (body.event or "").strip(),
            extra_date=(body.date or "").strip() or None,
            time_label=now_cl.strftime("%H:%M"),
            lang=str(body.lang or "es"),
            referrer=str(body.referrer or ""),
            is_returning=bool(body.is_returning),
            recorded_at=now_cl,
        )
    except Exception as _persist_e:
        logger.warning("visitor event persist failed: %s", _persist_e)

    if get_setting("booking_visitor_notif", "false").lower() != "true":
        return {"ok": True, "sent": False}

    if sid not in _visitor_sessions:
        _visitor_sessions[sid] = {
            "session_id": sid,
            "start_time": now_cl,
            "lang": body.lang or "es",
            "referrer": "",
            "is_returning": body.is_returning or False,
            "events": [],
            "utm_source": "",
            "utm_medium": "",
            "utm_campaign": "",
            "utm_content": "",
            "parametro_url": "",
            "fbclid": False,
        }
    sess = _visitor_sessions[sid]
    _merge_visitor_session_attribution(sess, body)
    if body.lang:
        sess["lang"] = body.lang or sess.get("lang") or "es"
    sess["is_returning"] = bool(sess.get("is_returning")) or bool(body.is_returning)

    _visitor_sessions[sid]["events"].append({
        "event": body.event,
        "date": body.date,
        "time": now_cl.strftime("%H:%M"),
    })
    _visitor_sessions[sid]["last_time"] = now_cl

    # Cancel existing 5-min timer, restart it (reset on each new event)
    if sid in _visitor_tasks and not _visitor_tasks[sid].done():
        _visitor_tasks[sid].cancel()
    _visitor_tasks[sid] = asyncio.create_task(_delayed_session_email(sid, 300))

    return {"ok": True, "sent": False}


async def _delayed_session_email(session_id: str, delay: int = 300):
    import asyncio
    try:
        await asyncio.sleep(delay)
        session = _visitor_sessions.pop(session_id, None)
        _visitor_tasks.pop(session_id, None)
        if session and session.get("events"):
            try:
                await asyncio.get_event_loop().run_in_executor(
                    None, _send_session_summary, session
                )
            except Exception as e:
                logger.warning("_delayed_session_email summary failed: %s", e)
    except asyncio.CancelledError:
        pass  # timer was reset by a new event; a new task was already scheduled


def _classify_visitor(events: list) -> tuple:
    types = {e["event"] for e in events}
    if "booking_completed" in types:
        return "✅ Reservó", "Completó una reserva en la página"
    if "solicitud_form" in types:
        return "🎯 Listo para reservar", "Abrió el formulario de solicitud de reserva"
    if "date_selected" in types:
        return "⭐ Muy interesado", "Seleccionó una fecha en el calendario"
    deep = types & {"view_prices", "view_alojamientos", "view_alojamiento_detail",
                    "view_experiencias", "view_packs", "view_arma_pack"}
    if "view_reservar" in types or len(deep) >= 2:
        return "🔍 Explorando activamente", "Visitó varias secciones y mostró interés real"
    if deep:
        return "🔍 Explorando", "Revisó algunas secciones de la página"
    return "👀 Solo mirando", "Entró a la página pero no interactuó mucho"


def _referrer_label(referrer: str) -> str:
    if not referrer:
        return ""
    r = referrer.lower()
    if "instagram" in r:      return "📸 Instagram"
    if "facebook" in r or "fb.com" in r: return "👥 Facebook"
    if "tiktok" in r:         return "🎵 TikTok"
    if "google" in r:         return "🔍 Google"
    if "whatsapp" in r or "wa.me" in r:  return "💬 WhatsApp"
    return referrer[:80]


_EVENT_LABELS = {
    "page_visit":             ("👀", "Entró a la página"),
    "view_reservar":          ("🗓️", "Fue al calendario de reservas"),
    "date_selected":          ("📅", "Seleccionó una fecha"),
    "view_prices":            ("💰", "Vio los precios"),
    "view_features":          ("⚡", "Vio las características del HotBoat"),
    "view_ubicacion":         ("📍", "Vio cómo llegar"),
    "view_alojamientos":      ("🏠", "Vio la lista de alojamientos"),
    "view_alojamiento_detail":("🔍", "Vio el detalle de un alojamiento"),
    "view_experiencias":      ("🎭", "Vio otras experiencias"),
    "view_packs":             ("📦", "Vio los packs completos"),
    "view_arma_pack":         ("🛠️", "Exploró Arma tu Pack"),
    "solicitud_form":         ("📋", "Abrió formulario de solicitud"),
    "booking_completed":      ("🎉", "Completó una reserva"),
    "exit":                   ("🚪", "Salió de la página"),
}


def _pretty_attribution_fragment(s: str) -> str:
    s = (s or "").strip()
    return s.replace("-", " ").replace("_", " ").title() if s else ""


def _build_ad_label(
    utm_campaign: str,
    parametro_url: str,
    utm_source: str,
    utm_medium: str,
    utm_content: str,
    from_fbclid: bool,
    referrer: str,
) -> str:
    """Return a human-readable ad label for the visitor session email."""
    if utm_campaign:
        return _pretty_attribution_fragment(utm_campaign)
    if parametro_url:
        return _pretty_attribution_fragment(parametro_url)
    # Often only utm_content is populated for Meta paid when campaign name is omitted
    if utm_content and not utm_campaign and not parametro_url:
        meta_med = utm_medium.lower() in ("paid", "cpc", "cpm", "paid_social", "paid social")
        if from_fbclid or meta_med:
            return _pretty_attribution_fragment(utm_content)
    if from_fbclid:
        r = referrer.lower()
        if "instagram" in r:
            return "Anuncio de Instagram"
        return "Anuncio de Facebook/Meta"
    return ""


def _send_session_summary(session: dict):
    from app.booking.visitor_tracking import persist_booking_visitor_session_closed

    ended_at = datetime.now(CHILE_TZ)
    events = session.get("events", []) or []
    classification, cls_desc = _classify_visitor(events)
    sent_ok = False

    try:
        from app.config import get_settings
        from app.booking.booking_email import _get_admin_email, _get_from_addr
        from app.email.resend_booking import send_booking_html

        cfg = get_settings()
        api_key   = (getattr(cfg, "resend_api_key", "") or "").strip()
        to_addr   = _get_admin_email(cfg)
        from_addr = _get_from_addr(cfg)
        lang         = (session.get("lang") or "es").upper()
        referrer     = session.get("referrer", "")
        is_returning = session.get("is_returning", False)
        start_time   = session.get("start_time")
        start_str    = start_time.strftime("%d/%m/%Y %H:%M") if start_time else "—"
        utm_campaign = (session.get("utm_campaign") or "").strip()
        utm_source   = (session.get("utm_source") or "").strip()
        utm_medium   = (session.get("utm_medium") or "").strip()
        utm_content  = (session.get("utm_content") or "").strip()
        parametro_url = (session.get("parametro_url") or "").strip()
        from_fbclid  = bool(session.get("fbclid"))

        if not api_key or not to_addr:
            logger.warning("visitor_session_summary: email not configured; skipping send")
        else:
            ref_label = _referrer_label(referrer)

            # Build ad source label
            ad_label = _build_ad_label(
                utm_campaign, parametro_url, utm_source, utm_medium, utm_content, from_fbclid, referrer
            )
            # Audience / creative variation: prefer utm_content when it is distinct from headline label
            base_for_audience = _pretty_attribution_fragment(utm_campaign or parametro_url)
            cand = _pretty_attribution_fragment(utm_content)
            audience_label = ""
            if cand and cand.casefold() != (base_for_audience or "").casefold():
                audience_label = cand

            rows = ""
            for ev in events:
                icon, label = _EVENT_LABELS.get(ev["event"], ("•", ev["event"]))
                extra = f" — <strong>{ev['date']}</strong>" if ev.get("date") else ""
                rows += (f'<tr>'
                         f'<td style="color:#888;font-size:.8rem;padding:.25rem .6rem;white-space:nowrap">{ev["time"]}</td>'
                         f'<td style="padding:.25rem .6rem">{icon} {label}{extra}</td>'
                         f'</tr>')

            ref_row = (f'<tr><td style="color:#888;padding:.3rem 0">Origen</td>'
                       f'<td><strong>{ref_label}</strong></td></tr>') if ref_label else ""

            ad_row = (f'<tr><td style="color:#888;padding:.3rem 0">📢 Anuncio</td>'
                      f'<td><strong style="color:#f5c842">{ad_label}</strong></td></tr>') if ad_label else ""
            audience_row = (f'<tr><td style="color:#888;padding:.3rem 0">👥 Audiencia</td>'
                            f'<td><strong style="color:#7eb8f7">{audience_label}</strong></td></tr>') if audience_label else ""

            subject = f"{classification} · {start_str}"
            html = f"""
<div style="font-family:sans-serif;max-width:520px;margin:auto;padding:1.5rem;
            background:#1a1a2e;color:#e0e0e0;border-radius:12px">
  <h2 style="color:#f5c842;margin-bottom:.2rem">Resumen de visita</h2>
  <p style="color:#888;margin-top:0;font-size:.85rem">{start_str}</p>

  <div style="background:#252540;border-radius:8px;padding:1rem;margin:1rem 0">
    <div style="font-size:1.3rem;margin-bottom:.3rem">{classification}</div>
    <div style="color:#aaa;font-size:.85rem">{cls_desc}</div>
  </div>

  <table style="width:100%;border-collapse:collapse;font-size:.85rem;margin-bottom:1rem">
    <tr>
      <td style="color:#888;padding:.3rem 0;width:45%">Idioma</td>
      <td><strong>{lang}</strong></td>
    </tr>
    <tr>
      <td style="color:#888;padding:.3rem 0">Tipo de visita</td>
      <td><strong>{'🔁 Visitante recurrente' if is_returning else '🆕 Primera visita'}</strong></td>
    </tr>
    {ref_row}
    {ad_row}
    {audience_row}
    <tr>
      <td style="color:#888;padding:.3rem 0">Acciones</td>
      <td><strong>{len(events)}</strong></td>
    </tr>
  </table>

  <div style="font-size:.8rem;color:#888;margin-bottom:.4rem">📋 Actividad registrada:</div>
  <table style="width:100%;font-size:.85rem;background:#252540;border-radius:8px;
                padding:.4rem;border-collapse:collapse">
    {rows}
  </table>
</div>"""

            send_booking_html(to=to_addr, subject=subject, html=html,
                              from_address=from_addr, api_key=api_key)
            sent_ok = True
            logger.info("visitor_session_summary sent: sid=%s events=%d cls=%s",
                        session.get("session_id", "?"), len(events), classification)
    except Exception as e:
        logger.warning("_send_session_summary error: %s", e)

    try:
        persist_booking_visitor_session_closed(
            session, classification, cls_desc, sent_ok, ended_at,
        )
    except Exception as pe:
        logger.warning("visitor_session DB persist failed: %s", pe)
