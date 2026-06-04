"""Mirror alojamiento lines from all_appointments.extras_json into extras_bookings (Calendario Extras)."""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def _sync_notes_marker(appointment_id: int) -> str:
    return f"__sync_appt_id:{appointment_id}__"


def _extras_json_to_flat_dict(raw: Any) -> Dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return {}
    if isinstance(raw, list):
        flat: Dict[str, Any] = {}
        for i, e in enumerate(raw):
            if isinstance(e, dict):
                name = str(e.get("name") or f"extra_{i}")
                key = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or f"extra_{i}"
                flat[key] = {"qty": e.get("quantity") or 1, "unit_price": e.get("price") or 0, "name": name}
        return flat
    if isinstance(raw, dict):
        inner = raw.get("extras")
        if isinstance(inner, list):
            return _extras_json_to_flat_dict(inner)
        skip = {"extras", "price_per_person"}
        return {k: dict(v) for k, v in raw.items() if k not in skip and isinstance(v, dict)}
    return {}


def _format_date(d: Any) -> Optional[str]:
    if d is None:
        return None
    if hasattr(d, "strftime"):
        return d.strftime("%Y-%m-%d")  # type: ignore[union-attr]
    s = str(d).strip()
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s[:10]
    return s or None


def _map_reserva_status_to_calendar(status: Optional[str]) -> str:
    s = (status or "").lower().strip()
    if s in ("confirmed", "confirmada", "confirmado", "completed", "paid"):
        return "confirmado"
    if s in ("cancelled", "cancelada", "cancelado", "rejected", "rechazada"):
        return "cancelado"
    return "pendiente"


def _calendar_booking_ref(source: str, source_id: Optional[str], appointment_id: int) -> str:
    """Ref shown in Calendario Extras: HB-* for web HotBoat row, else AA-{id}."""
    if (source or "").strip() == "hotboat_web" and (source_id or "").strip():
        return str(source_id).strip()
    return f"AA-{appointment_id}"


def _hotboat_has_accommodation_row(cur, hotboat_ref: str) -> bool:
    if not (hotboat_ref or "").strip():
        return False
    cur.execute(
        "SELECT 1 FROM accommodation_bookings "
        "WHERE hotboat_ref IS NOT NULL AND TRIM(hotboat_ref) = TRIM(%s) LIMIT 1",
        (hotboat_ref.strip(),),
    )
    return cur.fetchone() is not None


def sync_aloj_addons_from_appointment_cursor(
    cur,
    *,
    appointment_id: int,
    source: str,
    source_id: Optional[str],
    extras_json: Any,
    nombre_cliente: str,
    telefono: Optional[str],
    num_personas: Optional[int],
    fecha: Any,
    status: Optional[str],
) -> None:
    """
    Upsert calendar rows for each aloj__* key in extras_json.
    For hotboat_web: skip if this HB already has a fila en accommodation_bookings
    (el calendario ya tiene la fila HA-* del checkout web).
    """
    marker = _sync_notes_marker(appointment_id)
    flat = _extras_json_to_flat_dict(extras_json)

    cur.execute("DELETE FROM extras_bookings WHERE notes LIKE %s", (f"%{marker}%",))

    src = (source or "").strip()
    sid = (source_id or "").strip()
    hb_ref = sid if src == "hotboat_web" else ""
    if src == "hotboat_web" and hb_ref and _hotboat_has_accommodation_row(cur, hb_ref):
        logger.info(
            "extras calendar sync skipped: HB %s already linked in accommodation_bookings",
            hb_ref,
        )
        return

    aloj_keys = sorted(k for k in flat if str(k).startswith("aloj__"))
    if not aloj_keys:
        if flat:
            logger.warning(
                "extras calendar sync: no aloj__* keys (appt_id=%s source=%s); keys=%s",
                appointment_id,
                src,
                list(flat.keys())[:30],
            )
        return

    booking_ref = _calendar_booking_ref(source, sid or None, appointment_id)
    nm = (nombre_cliente or "").strip() or "Cliente"
    phone = (telefono or "").strip() or None
    npeople = int(num_personas or 1)
    default_start = _format_date(fecha)
    cal_status = _map_reserva_status_to_calendar(status)

    for key in aloj_keys:
        val = flat[key] or {}
        if not isinstance(val, dict):
            continue
        slug = str(key).replace("aloj__", "", 1).strip() or "alojamiento"
        nights = int(float(val.get("qty") or val.get("nights") or 1))
        unit_price = int(float(val.get("unit_price") or 0))
        name = (val.get("name") or "").strip() or slug.replace("_", " ").title()
        start_s = (val.get("entry_date") or val.get("check_in") or default_start) or default_start
        if not start_s:
            logger.warning("extras calendar sync: no start date for %s appt %s", key, appointment_id)
            continue
        end_s = val.get("exit_date") or val.get("check_out") or start_s
        total_line = nights * unit_price
        notes = f"{marker} Panel reservas · {key}"

        cur.execute(
            """
            INSERT INTO extras_bookings (
                booking_ref, customer_name, customer_phone, item_type, item_slug, item_name,
                start_date, end_date, num_people, total_price, deposit_paid, status, notes
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                booking_ref,
                nm,
                phone,
                "alojamiento",
                slug[:512],
                name[:512],
                start_s,
                end_s,
                npeople,
                total_line,
                0,
                cal_status,
                notes[:2000] if len(notes) > 2000 else notes,
            ),
        )
    logger.info(
        "extras_bookings sync from admin: appt_id=%s rows=%s booking_ref=%s",
        appointment_id,
        len(aloj_keys),
        booking_ref,
    )


def update_synced_aloj_calendar_status(cur, appointment_id: int, status: Optional[str]) -> None:
    """When only reserva status changes, keep linked extras_bookings rows in sync."""
    marker = _sync_notes_marker(appointment_id)
    cal_status = _map_reserva_status_to_calendar(status)
    cur.execute(
        "UPDATE extras_bookings SET status=%s WHERE notes LIKE %s",
        (cal_status, f"%{marker}%"),
    )
