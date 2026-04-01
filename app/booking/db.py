"""Database operations for hotboat_appointments"""
import logging, json, random, string
from datetime import datetime
from typing import List, Optional
from zoneinfo import ZoneInfo
from app.db.connection import get_connection

CHILE_TZ = ZoneInfo("America/Santiago")
logger = logging.getLogger(__name__)
PRICES = {2: 69990, 3: 54990, 4: 44990, 5: 38990, 6: 32990, 7: 29990}


def generate_booking_ref() -> str:
    year = datetime.now(CHILE_TZ).year
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=5))
    return f"HB-{year}-{suffix}"


def create_booking(data: dict) -> dict:
    ref = generate_booking_ref()
    with get_connection() as conn:
        with conn.cursor() as cur:
            sql = (
                "INSERT INTO hotboat_appointments"
                " (booking_ref,customer_name,customer_phone,customer_email,"
                "  booking_date,booking_time,num_people,"
                "  price_per_person,subtotal,extras_total,flex_amount,total_price,"
                "  extras,has_flex,status,source,notes)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'pending_payment',%s,%s)"
                " RETURNING id,booking_ref,status"
            )
            cur.execute(sql, (
                ref,
                data["customer_name"], data["customer_phone"], data.get("customer_email"),
                data["booking_date"], data["booking_time"], data["num_people"],
                data["price_per_person"], data["subtotal"],
                data.get("extras_total", 0), data.get("flex_amount", 0), data["total_price"],
                json.dumps(data.get("extras", [])), data.get("has_flex", False),
                data.get("source", "web"), data.get("notes")
            ))
            row = cur.fetchone()
            conn.commit()
            return {"id": row[0], "booking_ref": row[1], "status": row[2]}


def update_booking_payment(booking_ref: str, payment_id: str, payment_order_id: str, payment_status: str) -> bool:
    new_status = "confirmed" if payment_status == "approved" else "pending_payment"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE hotboat_appointments"
                " SET payment_id=%s, payment_order_id=%s, payment_status=%s, status=%s,"
                "     paid_at=CASE WHEN %s='approved' THEN NOW() ELSE paid_at END"
                " WHERE booking_ref=%s",
                (payment_id, payment_order_id, payment_status, new_status, payment_status, booking_ref)
            )
            conn.commit()
            return cur.rowcount > 0


def get_booking_by_ref(booking_ref: str) -> Optional[dict]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id,booking_ref,customer_name,customer_phone,customer_email,"
                "       booking_date,booking_time,num_people,price_per_person,"
                "       subtotal,extras_total,flex_amount,total_price,"
                "       extras,has_flex,status,payment_id,payment_status,"
                "       paid_at,source,notes,created_at"
                " FROM hotboat_appointments WHERE booking_ref=%s",
                (booking_ref,)
            )
            row = cur.fetchone()
            if not row:
                return None
            cols = ["id","booking_ref","customer_name","customer_phone","customer_email",
                    "booking_date","booking_time","num_people","price_per_person",
                    "subtotal","extras_total","flex_amount","total_price",
                    "extras","has_flex","status","payment_id","payment_status",
                    "paid_at","source","notes","created_at"]
            result = dict(zip(cols, row))
            for k in ("booking_date","booking_time","paid_at","created_at"):
                if result.get(k):
                    result[k] = str(result[k])
            return result


def get_all_bookings(limit: int = 200) -> List[dict]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id,booking_ref,customer_name,customer_phone,"
                "       booking_date,booking_time,num_people,total_price,status,created_at"
                " FROM hotboat_appointments ORDER BY created_at DESC LIMIT %s",
                (limit,)
            )
            cols = ["id","booking_ref","customer_name","customer_phone",
                    "booking_date","booking_time","num_people","total_price","status","created_at"]
            rows = cur.fetchall()
            result = []
            for r in rows:
                d = dict(zip(cols, r))
                for k in ("booking_date","booking_time","created_at"):
                    if d.get(k):
                        d[k] = str(d[k])
                result.append(d)
            return result
