"""
Reconciles a completed Transbank payment back into HotBoat's booking tables.

New, deliberately separate from the WooCommerce webhook in admin_router.py
(POST /api/woo-webhook) — that code stays untouched and dormant once the
call sites in router.py stop feeding WooCommerce orders, so rolling back to
WooCommerce (if ever needed) only means reverting the call-site changes,
not touching this file or that one.

`buy_order` is always one of the booking_ref values HotBoat already
generates (all_appointments.source_id, accommodation_bookings.booking_ref,
or extras_bookings.booking_ref) — there is no external order id to
correlate, since Transbank was given the booking_ref itself as buy_order at
creation time. This mirrors the exact same cascade the WooCommerce webhook
already performs (all_appointments -> accommodation_bookings -> combined
hotboat_ref -> extras_bookings mirror -> experience/pack extras_bookings),
just resolved by trying each table in turn instead of via WooCommerce order
meta_data.
"""
import logging

logger = logging.getLogger(__name__)


def confirm_payment_by_ref(buy_order: str, payment_id: str | None, status: str, amount: float | None = None) -> bool:
    """status is 'approved' or 'rejected'. Returns True if some booking was
    found and updated (regardless of which table it lived in)."""
    buy_order = (buy_order or "").strip()
    if not buy_order:
        return False

    if _confirm_hotboat_booking(buy_order, payment_id, status, amount):
        return True
    if _confirm_accommodation_booking(buy_order, payment_id, status):
        return True
    if _confirm_extras_booking(buy_order, payment_id, status):
        return True

    logger.warning("Transbank confirm: no booking found for buy_order=%s", buy_order)
    return False


def _record_pago(buy_order: str, payment_id: str | None, status: str, amount: float | None) -> None:
    """Append this charge to all_appointments.pagos — the WooCommerce webhook
    (admin_router.py's /api/woo-webhook) used to be what filled this column
    for Transbank payments; the admin-force confirmation email sums it to
    show the real amount paid (see send_confirmation_admin_force in
    booking_email.py), so without this it always showed $0 for bookings
    confirmed through this direct integration. Dedup on authorization_code
    so a duplicate /api/transbank/return hit doesn't double-count."""
    if amount is None or amount <= 0:
        return
    from app.db.connection import get_connection
    import json as _json
    from datetime import date as _date

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, COALESCE(pagos,'[]'::jsonb) FROM all_appointments"
                " WHERE source='hotboat_web' AND TRIM(source_id)=TRIM(%s)",
                (buy_order,),
            )
            row = cur.fetchone()
            if not row:
                return
            booking_id, pagos_raw = row
            pagos = list(pagos_raw) if pagos_raw else []
            already = any(p.get("authorization_code") == payment_id for p in pagos if payment_id)
            if already:
                return
            pagos.append({
                "amount": float(amount),
                "method": "transbank",
                "authorization_code": payment_id,
                "date": _date.today().isoformat(),
                "status": status,
            })
            cur.execute(
                "UPDATE all_appointments SET pagos=%s, updated_at=NOW() WHERE id=%s",
                (_json.dumps(pagos), booking_id),
            )
            conn.commit()


def _confirm_hotboat_booking(buy_order: str, payment_id: str | None, status: str, amount: float | None = None) -> bool:
    from app.booking.db import update_booking_payment, get_booking_by_ref

    updated = update_booking_payment(buy_order, payment_id or "", buy_order, status)
    if not updated:
        return False

    if status == "approved":
        try:
            _record_pago(buy_order, payment_id, status, amount)
        except Exception as pago_err:
            logger.warning(f"Transbank confirm: pagos record error for {buy_order}: {pago_err}")

    logger.info("Transbank confirm: all_appointments %s -> %s", buy_order, status)
    try:
        from app.booking.booking_email import try_send_booking_confirmation_after_payment
        try_send_booking_confirmation_after_payment(buy_order)
    except Exception as em_err:
        logger.warning(f"Transbank confirm: confirmation email error: {em_err}")

    try:
        booking = get_booking_by_ref(buy_order)
        if booking and status == "approved":
            phone = (booking.get("customer_phone") or "").strip()
            total = float(booking.get("total_price") or booking.get("subtotal") or 0)
            if phone and total > 0:
                import asyncio
                from app.meta.conversions import fire_purchase_from_booking
                asyncio.create_task(fire_purchase_from_booking(phone, total))
    except Exception as capi_err:
        logger.warning(f"Transbank confirm: Meta CAPI Purchase failed: {capi_err}")

    return True


def _confirm_accommodation_booking(buy_order: str, payment_id: str | None, status: str) -> bool:
    from app.db.connection import get_connection

    new_status = "confirmed" if status == "approved" else "rejected"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE accommodation_bookings"
                " SET status=%s, payment_order_id=%s, payment_status=%s,"
                "     paid_at=CASE WHEN %s='approved' THEN NOW() ELSE paid_at END, updated_at=NOW()"
                " WHERE booking_ref=%s"
                " RETURNING hotboat_ref, customer_name, customer_phone, customer_email,"
                "           accommodation_name, check_in, check_out, total_price, deposit_amount",
                (new_status, payment_id or "", status, status, buy_order),
            )
            row = cur.fetchone()
            if not row:
                return False
            (hotboat_ref, cname, cphone, cemail, aloj_name,
             check_in, check_out, total, deposit) = row

            try:
                cur.execute(
                    "UPDATE extras_bookings SET status=%s, total_price=%s, deposit_paid=%s "
                    "WHERE booking_ref=%s AND item_type='alojamiento'",
                    ("confirmado" if status == "approved" else "rechazado",
                     int(total or 0), int(deposit or 0), buy_order),
                )
            except Exception as ee:
                logger.warning("Transbank confirm: extras_bookings mirror failed for %s: %s", buy_order, ee)

            if hotboat_ref and status == "approved":
                cur.execute(
                    "UPDATE all_appointments"
                    " SET status='confirmed', payment_order_id=%s, payment_status=%s,"
                    "     paid_at=NOW(), updated_at=NOW()"
                    " WHERE source='hotboat_web' AND TRIM(source_id)=TRIM(%s)",
                    (payment_id or "", status, hotboat_ref),
                )
            conn.commit()

    logger.info("Transbank confirm: accommodation_bookings %s -> %s", buy_order, new_status)

    if status == "approved":
        nights = (check_out - check_in).days if check_in and check_out else 0
        try:
            from app.booking.router import _notify_aloj_booking
            import asyncio
            asyncio.create_task(_notify_aloj_booking(
                aloj_ref=buy_order, accommodation_name=aloj_name or "",
                customer_name=cname or "", customer_phone=cphone or "",
                check_in=check_in.strftime("%d/%m/%Y") if check_in else "",
                check_out=check_out.strftime("%d/%m/%Y") if check_out else "",
                nights=nights, total=float(total or 0), deposit=float(deposit or 0),
                hotboat_ref=hotboat_ref, confirmed=True,
            ))
        except Exception as wn:
            logger.warning("Transbank confirm: aloj WhatsApp notify error: %s", wn)
        try:
            import threading
            from app.booking.router import _email_aloj_booking
            threading.Thread(
                target=_email_aloj_booking,
                kwargs=dict(
                    aloj_ref=buy_order, accommodation_name=aloj_name or "",
                    customer_name=cname or "", customer_phone=cphone or "", customer_email=cemail or "",
                    check_in=check_in.strftime("%d/%m/%Y") if check_in else "",
                    check_out=check_out.strftime("%d/%m/%Y") if check_out else "",
                    nights=nights, total=float(total or 0), deposit=float(deposit or 0),
                    hotboat_ref=hotboat_ref, confirmed=True,
                ),
                daemon=True,
            ).start()
        except Exception as en:
            logger.warning("Transbank confirm: aloj email notify error: %s", en)

    return True


def _confirm_extras_booking(buy_order: str, payment_id: str | None, status: str) -> bool:
    from app.db.connection import get_connection

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT total_price, deposit_paid FROM extras_bookings "
                "WHERE booking_ref=%s AND item_type IN ('experience', 'pack') LIMIT 1",
                (buy_order,),
            )
            row = cur.fetchone()
            if not row:
                return False
            total_price, deposit_paid = row
            cur.execute(
                "UPDATE extras_bookings SET status=%s, total_price=%s, deposit_paid=%s "
                "WHERE booking_ref=%s AND item_type IN ('experience', 'pack')",
                ("confirmado" if status == "approved" else "rechazado",
                 int(total_price or 0), int(deposit_paid or 0), buy_order),
            )
            conn.commit()

    logger.info("Transbank confirm: extras_bookings %s -> %s", buy_order, status)
    return True
