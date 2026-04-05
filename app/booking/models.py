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
    booking_date: str
    booking_time: str
    num_people: int
    extras: List[ExtraItem] = []
    has_flex: bool = False
    notes: Optional[str] = None
    source: str = "web"
    test_price: Optional[int] = None  # Override total for testing (e.g. 100 CLP)


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
