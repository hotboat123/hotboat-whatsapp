"""
Gift cards — "regala una experiencia HotBoat" sin tener que elegir fecha
hoy: se paga el 100% al comprar (a diferencia de una reserva normal, que
cobra 50% de pie porque el saldo se cobra al llegar en una fecha real —
una gift card no tiene fecha hasta que se canjea, así que no hay "al
llegar" para cobrar el resto). El destinatario elige fecha más adelante
(canje — no implementado todavía, ver redeemed_at/redeemed_booking_ref).

Vive en su propia tabla (no all_appointments/extras_bookings) porque
ambas tienen su columna de fecha NOT NULL — no hay forma de representar
"sin fecha todavía" en ninguna de las dos sin volverlas nullable, lo que
tocaría todo el resto del sistema que sí asume fecha real.
"""
import logging
import random
import string
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from app.db.connection import get_connection
from app.booking.db import PRICES, price_breakdown, CHILE_TZ

logger = logging.getLogger(__name__)

gift_cards_router = APIRouter()

GIFT_CARD_VALIDITY_YEARS = 2


def _check_auth(key: str):
    pass  # Same no-op as every other admin router here — see admin_router.py's _check_auth

_gift_cards_table_ensured = False


def _ensure_gift_cards_table(cur) -> None:
    """Self-migrating, same pattern as the rest of this app (see e.g.
    _ensure_unanswered_alerts_table in webhook.py) — runs once per process."""
    global _gift_cards_table_ensured
    if _gift_cards_table_ensured:
        return
    cur.execute("""
        CREATE TABLE IF NOT EXISTS gift_cards (
            id                    SERIAL PRIMARY KEY,
            code                  TEXT UNIQUE NOT NULL,
            num_adultos           INT NOT NULL,
            num_ninos             INT NOT NULL DEFAULT 0,
            price_pp              INT NOT NULL,
            amount                INT NOT NULL,
            buyer_name            TEXT NOT NULL,
            buyer_phone           TEXT NOT NULL,
            buyer_email           TEXT,
            recipient_name        TEXT,
            dedication            TEXT,
            sender_name           TEXT,
            status                TEXT NOT NULL DEFAULT 'pending_payment',
            payment_id            TEXT,
            payment_order_id      TEXT,
            payment_status        TEXT,
            paid_at               TIMESTAMPTZ,
            purchased_at          TIMESTAMPTZ,
            expires_at            TIMESTAMPTZ,
            redeemed_at           TIMESTAMPTZ,
            redeemed_booking_ref  TEXT,
            email_sent_at         TIMESTAMPTZ,
            created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_gift_cards_code ON gift_cards(code)")
    # Admin-filled after contacting the buyer — same two fields/values as
    # all_appointments.ciudad_origen/como_supieron (see openModal in
    # admin-bookings.html), added later so ALTER instead of the CREATE above.
    cur.execute("ALTER TABLE gift_cards ADD COLUMN IF NOT EXISTS ciudad_origen TEXT")
    cur.execute("ALTER TABLE gift_cards ADD COLUMN IF NOT EXISTS como_supieron TEXT")
    _gift_cards_table_ensured = True


def generate_gift_card_code() -> str:
    """GC- prefix (distinct from HB- normal bookings, accommodation/extras
    refs) so the Transbank confirm cascade and the frontend's payment-return
    handler can both recognize a gift-card ref on sight, no DB lookup
    needed to know which table to check first."""
    year = datetime.now(CHILE_TZ).year
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"GC-{year}-{suffix}"


def is_gift_card_ref(ref: str) -> bool:
    return (ref or "").strip().upper().startswith("GC-")


class CreateGiftCardRequest(BaseModel):
    buyer_name: str
    buyer_phone: str
    buyer_email: Optional[str] = None
    num_adultos: int = 1
    num_ninos: int = 0
    recipient_name: Optional[str] = None
    dedication: Optional[str] = None
    sender_name: Optional[str] = None
    test_price: Optional[int] = None


@gift_cards_router.post("/api/gift-cards/create")
async def create_gift_card_endpoint(request: CreateGiftCardRequest):
    try:
        adults, children = request.num_adultos, request.num_ninos
        n = adults + children
        if adults < 1:
            raise HTTPException(status_code=400, detail="Se requiere al menos 1 adulto")
        if children < 0:
            raise HTTPException(status_code=400, detail="Cantidad de niños inválida")
        if not (2 <= n <= 7):
            raise HTTPException(status_code=400, detail="Capacidad: 2-7 personas (adultos + niños)")
        if not request.buyer_name.strip() or not request.buyer_phone.strip():
            raise HTTPException(status_code=400, detail="Faltan datos del comprador")

        # Precio base de tabla, SIEMPRE recalculado en el servidor — igual
        # que /api/booking/create. Sin precio dinámico: ese depende de la
        # fecha/hora de la reserva, que acá todavía no existe.
        price_pp = PRICES.get(n, 76990)
        amount = price_breakdown(adults, children, price_pp)["subtotal"]
        if request.test_price is not None and request.test_price > 0:
            amount = request.test_price

        code = generate_gift_card_code()
        with get_connection() as conn:
            with conn.cursor() as cur:
                _ensure_gift_cards_table(cur)
                cur.execute("""
                    INSERT INTO gift_cards
                        (code, num_adultos, num_ninos, price_pp, amount,
                         buyer_name, buyer_phone, buyer_email,
                         recipient_name, dedication, sender_name, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending_payment')
                """, (
                    code, adults, children, price_pp, amount,
                    request.buyer_name.strip(), request.buyer_phone.strip(),
                    (request.buyer_email or "").strip() or None,
                    (request.recipient_name or "").strip() or None,
                    (request.dedication or "").strip() or None,
                    (request.sender_name or "").strip() or None,
                ))
                conn.commit()

        from app.booking.router import _create_transbank_payment
        payment_url = await _create_transbank_payment(code, amount)

        return {"code": code, "status": "pending_payment", "amount": amount, "payment_url": payment_url}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Create gift card error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def get_gift_card_by_code(code: str) -> Optional[dict]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            _ensure_gift_cards_table(cur)
            cur.execute("""
                SELECT code, num_adultos, num_ninos, amount, buyer_name, buyer_phone,
                       buyer_email, recipient_name, dedication, sender_name, status,
                       purchased_at, expires_at, redeemed_at, redeemed_booking_ref
                FROM gift_cards WHERE code = %s
            """, (code,))
            row = cur.fetchone()
    if not row:
        return None
    (code, adults, children, amount, buyer_name, buyer_phone, buyer_email,
     recipient_name, dedication, sender_name, status,
     purchased_at, expires_at, redeemed_at, redeemed_booking_ref) = row
    return {
        "code": code,
        "num_adultos": adults,
        "num_ninos": children,
        "num_people": adults + children,
        "amount": amount,
        "buyer_name": buyer_name,
        "buyer_phone": buyer_phone,
        "buyer_email": buyer_email,
        "recipient_name": recipient_name,
        "dedication": dedication,
        "sender_name": sender_name,
        "status": status,
        "purchased_at": purchased_at.isoformat() if purchased_at else None,
        "expires_at": expires_at.isoformat() if expires_at else None,
        "redeemed_at": redeemed_at.isoformat() if redeemed_at else None,
        "redeemed_booking_ref": redeemed_booking_ref,
    }


@gift_cards_router.get("/api/gift-cards/{code}")
async def get_gift_card_endpoint(code: str):
    gc = get_gift_card_by_code(code)
    if not gc:
        raise HTTPException(status_code=404, detail="Gift card no encontrada")
    return gc


@gift_cards_router.get("/api/admin/gift-cards")
async def list_gift_cards_endpoint(x_admin_key: str = Header("")):
    """Panel admin (pestaña Gift Cards) — todas, más recientes primero. El
    canje en sí se hace a mano hoy (el dueño lo confirma por WhatsApp/en
    persona con el código) — esto solo da visibilidad + un botón para
    marcarla canjeada, no un flujo de autoservicio para el destinatario."""
    _check_auth(x_admin_key)
    with get_connection() as conn:
        with conn.cursor() as cur:
            _ensure_gift_cards_table(cur)
            cur.execute("""
                SELECT code, num_adultos, num_ninos, amount, buyer_name, buyer_phone,
                       buyer_email, recipient_name, dedication, sender_name, status,
                       purchased_at, expires_at, redeemed_at, redeemed_booking_ref, created_at,
                       ciudad_origen, como_supieron, payment_id, payment_status
                FROM gift_cards ORDER BY created_at DESC
            """)
            rows = cur.fetchall()
    return [
        {
            "code": r[0], "num_adultos": r[1], "num_ninos": r[2], "num_people": r[1] + r[2],
            "amount": r[3], "buyer_name": r[4], "buyer_phone": r[5], "buyer_email": r[6],
            "recipient_name": r[7], "dedication": r[8], "sender_name": r[9], "status": r[10],
            "purchased_at": r[11].isoformat() if r[11] else None,
            "expires_at": r[12].isoformat() if r[12] else None,
            "redeemed_at": r[13].isoformat() if r[13] else None,
            "redeemed_booking_ref": r[14],
            "created_at": r[15].isoformat() if r[15] else None,
            "ciudad_origen": r[16],
            "como_supieron": r[17],
            "payment_id": r[18],
            "payment_status": r[19],
            "is_expired": bool(r[10] == "active" and r[12] and r[12] < datetime.now(r[12].tzinfo)),
        }
        for r in rows
    ]


class UpdateGiftCardOriginRequest(BaseModel):
    ciudad_origen: Optional[str] = None
    como_supieron: Optional[str] = None


@gift_cards_router.put("/api/admin/gift-cards/{code}/origin")
async def update_gift_card_origin_endpoint(code: str, body: UpdateGiftCardOriginRequest, x_admin_key: str = Header("")):
    """Guarda ciudad_origen/como_supieron — igual que en reservas, esto lo
    llena el staff a mano después de hablar con el comprador, no se pide en
    el formulario web de compra."""
    _check_auth(x_admin_key)
    with get_connection() as conn:
        with conn.cursor() as cur:
            _ensure_gift_cards_table(cur)
            cur.execute("""
                UPDATE gift_cards
                SET ciudad_origen = %s, como_supieron = %s, updated_at = NOW()
                WHERE code = %s
                RETURNING id
            """, (
                (body.ciudad_origen or "").strip() or None,
                (body.como_supieron or "").strip() or None,
                code,
            ))
            row = cur.fetchone()
            conn.commit()
    if not row:
        raise HTTPException(status_code=404, detail="Gift card no encontrada")
    return {"ok": True}


class RedeemGiftCardRequest(BaseModel):
    redeemed_booking_ref: Optional[str] = None


@gift_cards_router.post("/api/admin/gift-cards/{code}/redeem")
async def redeem_gift_card_endpoint(code: str, body: RedeemGiftCardRequest, x_admin_key: str = Header("")):
    """Marca la gift card canjeada a mano — no valida fecha de vencimiento
    acá a propósito, el dueño ya la está viendo y decidiendo caso a caso."""
    _check_auth(x_admin_key)
    with get_connection() as conn:
        with conn.cursor() as cur:
            _ensure_gift_cards_table(cur)
            cur.execute("""
                UPDATE gift_cards
                SET status = 'redeemed', redeemed_at = NOW(),
                    redeemed_booking_ref = %s, updated_at = NOW()
                WHERE code = %s AND status = 'active'
                RETURNING id
            """, (body.redeemed_booking_ref, code))
            row = cur.fetchone()
            conn.commit()
    if not row:
        raise HTTPException(status_code=404, detail="Gift card no encontrada o no está activa")
    return {"ok": True}


@gift_cards_router.post("/api/admin/gift-cards/{code}/unredeem")
async def unredeem_gift_card_endpoint(code: str, x_admin_key: str = Header("")):
    """Deshace un canje marcado por error."""
    _check_auth(x_admin_key)
    with get_connection() as conn:
        with conn.cursor() as cur:
            _ensure_gift_cards_table(cur)
            cur.execute("""
                UPDATE gift_cards
                SET status = 'active', redeemed_at = NULL,
                    redeemed_booking_ref = NULL, updated_at = NOW()
                WHERE code = %s AND status = 'redeemed'
                RETURNING id
            """, (code,))
            row = cur.fetchone()
            conn.commit()
    if not row:
        raise HTTPException(status_code=404, detail="Gift card no encontrada o no está canjeada")
    return {"ok": True}


def confirm_gift_card_payment(code: str, payment_id: Optional[str], status: str, amount: Optional[float] = None) -> bool:
    """Called from the Transbank confirm cascade (app/payment/transbank_confirm.py)
    — mirrors _confirm_hotboat_booking's shape (returns True iff a gift_cards
    row with this code exists, regardless of approved/rejected)."""
    new_status = "active" if status == "approved" else "rejected"
    with get_connection() as conn:
        with conn.cursor() as cur:
            _ensure_gift_cards_table(cur)
            # GIFT_CARD_VALIDITY_YEARS is embedded directly (not a %s param)
            # — it's a fixed int constant, not user input, and INTERVAL
            # doesn't accept a bind parameter for its unit count anyway.
            cur.execute(f"""
                UPDATE gift_cards
                SET status = %s,
                    payment_id = %s,
                    payment_order_id = %s,
                    payment_status = %s,
                    paid_at = CASE WHEN %s = 'approved' THEN NOW() ELSE paid_at END,
                    purchased_at = CASE WHEN %s = 'approved' THEN NOW() ELSE purchased_at END,
                    expires_at = CASE WHEN %s = 'approved' THEN NOW() + INTERVAL '{GIFT_CARD_VALIDITY_YEARS} years' ELSE expires_at END,
                    updated_at = NOW()
                WHERE code = %s
                RETURNING id
            """, (new_status, payment_id or "", code, status, status, status, status, code))
            row = cur.fetchone()
            conn.commit()
    if not row:
        return False

    logger.info(f"Transbank confirm: gift_cards {code} -> {new_status}")
    if status == "approved":
        try:
            _send_gift_card_email(code)
        except Exception as e:
            logger.warning(f"Gift card confirmation email error for {code}: {e}")
    return True


def _send_gift_card_email(code: str) -> None:
    gc = get_gift_card_by_code(code)
    if not gc or not gc.get("buyer_email"):
        return
    from app.email.send_email import send_email
    from app.config import get_settings

    settings = get_settings()
    from_address = (
        (settings.resend_from_confirmations or "").strip()
        or (settings.email_from or "").strip()
        or "onboarding@resend.dev"
    )
    n = gc["num_people"]
    expires = gc.get("expires_at", "")[:10]
    expires_str = ""
    if expires:
        y, m, d = expires.split("-")
        expires_str = f"{d}/{m}/{y}"
    dedication_html = ""
    if gc.get("recipient_name") or gc.get("dedication"):
        dedication_html = f"""
        <div style="background:#faf5ff;border:1px solid #e9d5ff;border-radius:10px;padding:1rem;margin:1rem 0">
          {f'<p style="margin:0 0 .4rem"><strong>Para:</strong> {gc["recipient_name"]}</p>' if gc.get("recipient_name") else ""}
          {f'<p style="margin:0;font-style:italic">&ldquo;{gc["dedication"]}&rdquo;</p>' if gc.get("dedication") else ""}
          {f'<p style="margin:.4rem 0 0"><strong>De:</strong> {gc["sender_name"]}</p>' if gc.get("sender_name") else ""}
        </div>"""
    html = f"""
    <div style="font-family:-apple-system,Segoe UI,Arial,sans-serif;max-width:560px;margin:0 auto;color:#1a1a1a">
      <h2 style="color:#0b6b5c">🎁 ¡Tu gift card HotBoat está lista!</h2>
      <p>Gracias por tu compra, {gc["buyer_name"]}.</p>
      {dedication_html}
      <div style="background:#f0fdf4;border:2px dashed #16a34a;border-radius:10px;padding:1.2rem;text-align:center;margin:1rem 0">
        <div style="font-size:.8rem;color:#666;text-transform:uppercase;letter-spacing:.05em">Código de tu gift card</div>
        <div style="font-size:1.6rem;font-weight:700;letter-spacing:.05em;color:#0b6b5c;margin-top:.3rem">{code}</div>
      </div>
      <p>Válida para <strong>{n} persona{"s" if n != 1 else ""}</strong> — experiencia HotBoat en Pucón.</p>
      <p>Duración: <strong>{GIFT_CARD_VALIDITY_YEARS} años</strong> desde la compra{f", vence el <strong>{expires_str}</strong>" if expires_str else ""}.</p>
      <p style="color:#666;font-size:.9rem">Para coordinar la fecha, escribe a HotBoat por WhatsApp o email con este código a mano.</p>
    </div>"""
    send_email(
        to=gc["buyer_email"],
        subject=f"🎁 Tu gift card HotBoat — {code}",
        html=html,
        from_address=from_address,
        trigger="gift_card_purchased",
    )
