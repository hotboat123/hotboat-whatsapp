"""Bidirectional sync between flujo_caja_movimientos and a Google Sheet.

No-ops cleanly (logs once, returns) when GOOGLE_SERVICE_ACCOUNT_JSON isn't
configured yet — the DB/API side of the ledger works standalone; this just
doesn't push/pull until credentials exist. See gastos_router.py's
GEMINI_API_KEY check for the same pattern.
"""
import json
import logging
from typing import Optional

from app.config import get_settings
from app.db.connection import get_connection

logger = logging.getLogger(__name__)

# Column order in the Sheet — A through J. "Saldo" (E) is a deliberate gap:
# it's a running balance the owner fills in himself (or via his own
# formula), the app never reads or writes it.
SHEET_COLUMNS = [
    "fecha", "descripcion", "cargos", "abonos", None,
    "categoria_1", "categoria_2", "observaciones", "facturado_o_iva", "origen",
]
LAST_COL = "J"

_client = None
_client_checked = False


def _get_sheet():
    """Return the target worksheet, or None if credentials aren't configured."""
    global _client, _client_checked
    settings = get_settings()
    if not settings.google_service_account_json or not settings.google_flujo_caja_sheet_id:
        if not _client_checked:
            logger.info("Sheets sync: GOOGLE_SERVICE_ACCOUNT_JSON/GOOGLE_FLUJO_CAJA_SHEET_ID no configurados — sync deshabilitado por ahora")
            _client_checked = True
        return None
    _client_checked = True
    try:
        if _client is None:
            import gspread
            from google.oauth2.service_account import Credentials
            info = json.loads(settings.google_service_account_json)
            scopes = ["https://www.googleapis.com/auth/spreadsheets"]
            creds = Credentials.from_service_account_info(info, scopes=scopes)
            _client = gspread.authorize(creds)
        sh = _client.open_by_key(settings.google_flujo_caja_sheet_id)
        return sh.sheet1
    except Exception as e:
        logger.error(f"Sheets sync: no se pudo abrir el Sheet: {e}")
        return None


def _row_values(mov: dict) -> list:
    def fmt(v):
        if v is None:
            return ""
        return str(v)
    return [fmt(mov.get(col, "")) if col else "" for col in SHEET_COLUMNS]


def push_row(mov_id: int) -> None:
    """Write one flujo_caja_movimientos row to its Sheet row (append if new)."""
    ws = _get_sheet()
    if ws is None:
        return
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, fecha, abonos, cargos, origen, categoria_1, categoria_2, "
                    "descripcion, observaciones, facturado_o_iva, sheet_row "
                    "FROM flujo_caja_movimientos WHERE id=%s", (mov_id,)
                )
                r = cur.fetchone()
                if not r:
                    return
                mov = {
                    "fecha": r[1], "abonos": r[2], "cargos": r[3], "origen": r[4],
                    "categoria_1": r[5], "categoria_2": r[6], "descripcion": r[7],
                    "observaciones": r[8], "facturado_o_iva": r[9],
                }
                sheet_row = r[10]
                values = _row_values(mov)

                if sheet_row:
                    ws.update(f"A{sheet_row}:{LAST_COL}{sheet_row}", [values])
                else:
                    ws.append_row(values, value_input_option="USER_ENTERED")
                    # Row count right after append — safe because this whole
                    # function only runs on the single scheduler-lock winner.
                    sheet_row = len(ws.get_all_values())

                cur.execute(
                    "UPDATE flujo_caja_movimientos SET sheet_row=%s, "
                    "sheet_snapshot=%s, pushed_at=NOW() WHERE id=%s",
                    (sheet_row, json.dumps(mov, default=str), mov_id),
                )
            conn.commit()
    except Exception as e:
        logger.error(f"Sheets push_row({mov_id}) failed: {e}")


def clear_row(mov_id: int) -> None:
    """Blank out a Sheet row on delete — never remove it (would shift every
    other row's stored sheet_row out from under it)."""
    ws = _get_sheet()
    if ws is None:
        return
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT sheet_row FROM flujo_caja_movimientos WHERE id=%s", (mov_id,))
                r = cur.fetchone()
        if r and r[0]:
            ws.update(f"A{r[0]}:{LAST_COL}{r[0]}", [[""] * len(SHEET_COLUMNS)])
    except Exception as e:
        logger.error(f"Sheets clear_row({mov_id}) failed: {e}")


def _cells_equal(a: dict, b: dict) -> bool:
    return _row_values(a) == _row_values(b)


def _parse_amount(raw: str) -> Optional[int]:
    """Strip $, spaces, and thousands separators (',' or '.') — the sheet
    may hold hand-typed currency text like "$6,970" or "6.970"; CLP has no
    cents, so keep only the digits."""
    raw = (raw or "").strip()
    if not raw:
        return None
    digits = "".join(c for c in raw if c.isdigit())
    return int(digits) if digits else None


def _parse_sheet_date(raw: str) -> Optional[str]:
    """ISO (our own pushes write this) first, then D/M/YYYY (Chilean hand
    entry) — explicit dayfirst so Postgres's default MDY parsing never
    silently swaps day/month on a human-typed date."""
    raw = (raw or "").strip()
    if not raw:
        return None
    from datetime import datetime
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    logger.warning(f"Sheets sync: fecha '{raw}' no se pudo parsear, se deja NULL")
    return None


def sync_once() -> dict:
    """One reconciliation pass: pull manual Sheet edits into the DB, then
    push any DB-side changes that haven't reached the Sheet yet."""
    ws = _get_sheet()
    if ws is None:
        return {"skipped": True}

    pulled = 0
    pushed = 0
    try:
        all_values = ws.get_all_values()
    except Exception as e:
        logger.error(f"Sheets sync_once: no se pudo leer el Sheet: {e}")
        return {"error": str(e)}

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, sheet_row, sheet_snapshot, fecha, abonos, cargos, origen, "
                "categoria_1, categoria_2, descripcion, observaciones, facturado_o_iva, updated_at "
                "FROM flujo_caja_movimientos"
            )
            rows = cur.fetchall()
            by_sheet_row = {r[1]: r for r in rows if r[1]}

            # 1) Sheet → DB: any data row (2+) that differs from its last-known snapshot.
            for idx, row_vals in enumerate(all_values[1:], start=2):
                if not any(c.strip() for c in row_vals[:2]):
                    continue  # blank Fecha AND Descripción (columns A, B) — not a real row yet
                sheet_mov = {col: (row_vals[i] if i < len(row_vals) else "") for i, col in enumerate(SHEET_COLUMNS) if col}

                existing = by_sheet_row.get(idx)
                if existing:
                    snapshot = existing[2] if isinstance(existing[2], dict) else (json.loads(existing[2]) if existing[2] else {})
                    if _cells_equal(sheet_mov, snapshot):
                        continue  # unchanged since last sync

                parsed_fecha = _parse_sheet_date(sheet_mov["fecha"])
                parsed_abonos = _parse_amount(sheet_mov["abonos"])
                parsed_cargos = _parse_amount(sheet_mov["cargos"])

                if existing:
                    cur.execute(
                        "UPDATE flujo_caja_movimientos SET fecha=%s, "
                        "abonos=%s, cargos=%s, origen=%s, "
                        "categoria_1=%s, categoria_2=%s, descripcion=%s, observaciones=%s, "
                        "facturado_o_iva=%s, sheet_snapshot=%s, updated_at=NOW(), pushed_at=NOW() "
                        "WHERE id=%s",
                        (parsed_fecha, parsed_abonos, parsed_cargos, sheet_mov["origen"],
                         sheet_mov["categoria_1"], sheet_mov["categoria_2"], sheet_mov["descripcion"],
                         sheet_mov["observaciones"], sheet_mov["facturado_o_iva"],
                         json.dumps(sheet_mov), existing[0]),
                    )
                else:
                    cur.execute(
                        "INSERT INTO flujo_caja_movimientos "
                        "(fecha, abonos, cargos, origen, categoria_1, categoria_2, descripcion, "
                        "observaciones, facturado_o_iva, sheet_row, sheet_snapshot, pushed_at) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())",
                        (parsed_fecha, parsed_abonos, parsed_cargos, sheet_mov["origen"],
                         sheet_mov["categoria_1"], sheet_mov["categoria_2"], sheet_mov["descripcion"],
                         sheet_mov["observaciones"], sheet_mov["facturado_o_iva"],
                         idx, json.dumps(sheet_mov)),
                    )
                pulled += 1
            conn.commit()

            # 2) DB → Sheet: rows changed since their last push (no sheet_row,
            # or updated_at moved past pushed_at — e.g. edited via the app's
            # own PUT endpoint after the last sync).
            cur.execute(
                "SELECT id FROM flujo_caja_movimientos WHERE sheet_row IS NULL "
                "OR updated_at > COALESCE(pushed_at, 'epoch')"
            )
            to_push = [r[0] for r in cur.fetchall()]

    for mov_id in to_push:
        push_row(mov_id)
        pushed += 1

    return {"pulled": pulled, "pushed": pushed}
