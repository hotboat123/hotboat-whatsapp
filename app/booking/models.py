"""Pydantic models for the booking platform"""
from pydantic import BaseModel, EmailStr
from typing import List, Optional, Dict, Any
from datetime import date, time


class ExtraItem(BaseModel):
    name: str
    price: int
    quantity: int = 1


class CreateBookingRequest(BaseModel):
    customer_name: str
    customer_phone: str
    customer_email: Optional[str] = None
    customer_birthday: Optional[str] = None  # YYYY-MM-DD, optional
    customer_language: Optional[str] = "es"  # es / en / pt
    booking_date: str
    booking_time: str
    num_people: int
    extras: List[ExtraItem] = []
    has_flex: bool = False
    notes: Optional[str] = None
    source: str = "web"
    coupon_code: Optional[str] = None
    coupon_discount: Optional[float] = None  # CLP off (base HotBoat + FLEX, same as web summary)
    coupon_extra_benefit: Optional[str] = None  # e.g. benefit text from coupons.extra_description
    test_price: Optional[int] = None  # Override total for testing (e.g. 100 CLP)
    skip_payment: bool = False         # Create booking in DB but skip WooCommerce order
    utm_source: Optional[str] = ""
    utm_medium: Optional[str] = ""
    utm_campaign: Optional[str] = ""
    utm_content: Optional[str] = ""
    parametro_url: Optional[str] = ""


class BookingResponse(BaseModel):
    id: int
    booking_ref: str
    customer_name: str
    customer_phone: str
    booking_date: str
    booking_time: str
    num_people: int
    total_price: int
    status: str
    payment_url: Optional[str] = None
