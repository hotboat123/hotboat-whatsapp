"""
Availability checker - queries PostgreSQL for appointment availability
"""
import logging
import re
from datetime import datetime, timedelta, time
from typing import Optional, List, Dict, Tuple
from zoneinfo import ZoneInfo

from app.db.queries import get_booked_slots, check_slot_availability
from app.availability.availability_config import (
    AVAILABILITY_CONFIG,
    get_service_config
)

logger = logging.getLogger(__name__)

# Timezone for Chile (same as app.db.queries — use ZoneInfo for booked-slot overlap)
CHILE_TZ = ZoneInfo("America/Santiago")

# Spanish month names
SPANISH_MONTHS = {
    'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4,
    'mayo': 5, 'junio': 6, 'julio': 7, 'agosto': 8,
    'septiembre': 9, 'octubre': 10, 'noviembre': 11, 'diciembre': 12,
    # Short forms
    'ene': 1, 'feb': 2, 'mar': 3, 'abr': 4,
    'may': 5, 'jun': 6, 'jul': 7, 'ago': 8,
    'sep': 9, 'oct': 10, 'nov': 11, 'dic': 12
}


class AvailabilityChecker:
    """Check availability by querying appointments database"""
    
    def __init__(self):
        self.config = AVAILABILITY_CONFIG
        self.phone_number = None
        self._last_booked_range = None
        self._last_booked_slots = None
    
    def set_phone_number(self, phone_number: str):
        """Set phone number for auto-priority assignment"""
        self.phone_number = phone_number
    
    async def _auto_set_priority_high(self, phone_number: str, reason: str):
        """
        Auto-assign priority 1 (high) to a conversation
        
        Args:
            phone_number: Contact phone number
            reason: Reason for high priority
        """
        try:
            from app.db.leads import update_lead_priority
            success = await update_lead_priority(phone_number, 1)
            if success:
                logger.info(f"🔴 Auto-assigned priority 1 to {phone_number}: {reason}")
            else:
                logger.warning(f"Failed to auto-assign priority to {phone_number}")
        except Exception as e:
            logger.error(f"Error auto-assigning priority: {e}")
    
    def _parse_spanish_date(self, message: str, current_year: int) -> Optional[datetime]:
        """
        Parse Spanish date from message (e.g., "14 de febrero", "18 de noviembre", "jueves 6 de noviembre")
        
        Args:
            message: User message
            current_year: Current year to use if not specified
        
        Returns:
            Parsed datetime or None if not found
        """
        message_lower = message.lower()
        now = datetime.now(CHILE_TZ)

        def build_date(month: int, day: int) -> Optional[datetime]:
            """Create a tz-aware date for the requested year, rolling to next year only if the day is before today (ignore time)."""
            try:
                parsed_date_naive = datetime(current_year, month, day, 0, 0, 0)
                parsed_date = parsed_date_naive.replace(tzinfo=CHILE_TZ)
                # Only move to next year if the whole calendar day is in the past, not just the time.
                if parsed_date.date() < now.date():
                    parsed_date_naive = datetime(current_year + 1, month, day, 0, 0, 0)
                    parsed_date = parsed_date_naive.replace(tzinfo=CHILE_TZ)
                return parsed_date
            except ValueError:
                return None
        
        # Remove day of week names if they appear at the start (optional - makes parsing more flexible)
        # Spanish day names: lunes, martes, miércoles, jueves, viernes, sábado, domingo
        day_names = ['lunes', 'martes', 'miércoles', 'miercoles', 'jueves', 'viernes', 'sábado', 'sabado', 'domingo']
        for day_name in day_names:
            # Remove day name if it's at the start of the message
            if message_lower.startswith(day_name + ' '):
                message_lower = message_lower[len(day_name):].strip()
        
        # Pattern 1: "14 de febrero", "18 de noviembre", "6 de noviembre" (after removing day name)
        pattern1 = r'(\d{1,2})\s+de\s+(' + '|'.join(SPANISH_MONTHS.keys()) + r')'
        match = re.search(pattern1, message_lower)
        if match:
            day = int(match.group(1))
            month_name = match.group(2)
            month = SPANISH_MONTHS.get(month_name)
            if month:
                return build_date(month, day)
        
        # Pattern 2: "febrero 14", "noviembre 18" (without "de")
        pattern2 = r'(' + '|'.join(SPANISH_MONTHS.keys()) + r')\s+(\d{1,2})'
        match = re.search(pattern2, message_lower)
        if match:
            month_name = match.group(1)
            day = int(match.group(2))
            month = SPANISH_MONTHS.get(month_name)
            if month:
                return build_date(month, day)
        
        # Pattern 3: "14 febrero" (without "de")
        pattern3 = r'(\d{1,2})\s+(' + '|'.join(SPANISH_MONTHS.keys()) + r')'
        match = re.search(pattern3, message_lower)
        if match:
            day = int(match.group(1))
            month_name = match.group(2)
            month = SPANISH_MONTHS.get(month_name)
            if month:
                return build_date(month, day)
        
        # Pattern 4: "14/02", "18/11" (DD/MM format)
        pattern4 = r'(\d{1,2})[/-](\d{1,2})'
        match = re.search(pattern4, message_lower)
        if match:
            day = int(match.group(1))
            month = int(match.group(2))
            if 1 <= month <= 12 and 1 <= day <= 31:
                return build_date(month, day)
        
        return None
    
    def parse_exact_date(self, message: str) -> Optional[datetime]:
        """
        Public wrapper to parse a specific calendar date from user message.
        Does not handle relative expressions like 'hoy' or 'mañana'.
        """
        now = datetime.now(CHILE_TZ)
        return self._parse_spanish_date(message, now.year)
    
    async def get_slots_for_date(self, date: datetime) -> List[Dict]:
        """
        Convenience helper to fetch available slots for a single date.
        
        Args:
            date: Target date (timezone-aware), time portion ignored
        
        Returns:
            List of available slot dictionaries for that date
        """
        normalized = date.replace(hour=0, minute=0, second=0, microsecond=0)
        start_date = normalized
        end_date = normalized.replace(hour=23, minute=59, second=59, microsecond=999999)
        slots = await self.get_available_slots(start_date, end_date)
        return await self._filter_to_web_bookable(slots)
    
    def _generate_time_slots_for_date(self, date: datetime, override_hours: list = None) -> List[datetime]:
        """Generate all possible time slots for a given date.
        Accepts each hour as int (hora entera), 'HH' o 'HH:MM' — soporta media hora."""
        slots = []
        date_obj = date.date() if isinstance(date, datetime) else date
        hours = override_hours if override_hours is not None else self.config.operating_hours
        for h in hours:
            if isinstance(h, int):
                hh, mm = h, 0
            else:
                parts = str(h).strip().split(":")
                try:
                    hh = int(parts[0])
                    mm = int(parts[1]) if len(parts) > 1 and parts[1] != "" else 0
                except (ValueError, IndexError):
                    continue
            if not (0 <= hh <= 23 and 0 <= mm <= 59):
                continue
            dt_naive = datetime.combine(date_obj, time(hh, mm))
            slots.append(dt_naive.replace(tzinfo=CHILE_TZ))
        return slots
    
    async def get_available_slots(
        self,
        start_date: datetime,
        end_date: datetime,
        party_size: Optional[int] = None,
        vacation_dates: Optional[set] = None,
    ) -> List[Dict]:
        """
        Get available time slots from database

        Args:
            start_date: Start date for search
            end_date: End date for search
            party_size: Number of people (optional)
            vacation_dates: pre-fetched vacation-day set (as str(date)) for
                this range, so a caller that already loaded it doesn't pay
                for a second identical query. Fetched internally if omitted.

        Returns:
            List of available slots with datetime info
        """
        try:
            # Get all booked slots
            booked_slots = await get_booked_slots(
                start_date,
                end_date,
                exclude_statuses=self.config.exclude_statuses
            )
            # Cache para que check_availability() pueda reusarlos en el filtro de
            # urgencia sin volver a golpear la DB con el mismo rango de fechas.
            self._last_booked_range = (start_date, end_date)
            self._last_booked_slots = booked_slots

            # Duración de paseo por día según el perfil asignado (Horario/Urgencia).
            # Días sin perfil con duración propia → usan la duración global.
            day_duration_map: dict = {}
            try:
                from app.booking.operator_settings import get_day_duration_map
                day_duration_map = get_day_duration_map(start_date.date(), end_date.date())
            except Exception as e:
                logger.warning("get_day_duration_map failed (continuing): %s", e, exc_info=True)

            def _dur_for(d) -> float:
                return float(day_duration_map.get(str(d), self.config.duration_hours))

            # Create booked time ranges for overlap checking, grouped by date
            # so the per-slot overlap check below is O(bookings that day)
            # instead of a full scan of every booking in the whole range.
            booked_ranges_by_date: dict = {}
            for slot in booked_slots:
                if slot['starts_at']:
                    dt = slot['starts_at']
                    if isinstance(dt, str):
                        dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))

                    # Calculate appointment range with buffer (duración del día de la reserva)
                    appointment_start = dt
                    appointment_duration = _dur_for(dt.date())
                    appointment_end = appointment_start + timedelta(hours=appointment_duration)

                    # Apply buffer
                    appointment_start_with_buffer = appointment_start - timedelta(hours=self.config.buffer_hours)
                    appointment_end_with_buffer = appointment_end + timedelta(hours=self.config.buffer_hours)

                    booked_ranges_by_date.setdefault(dt.date(), []).append({
                        'start': appointment_start_with_buffer,
                        'end': appointment_end_with_buffer,
                    })
            
            # Load vacation days (unless the caller already fetched them for this
            # exact range) + operating hours (urgency is handled separately in the
            # web booking endpoint as a "ghost calendar" overlay; it must NOT affect
            # real availability generation here).
            need_vacation_fetch = vacation_dates is None
            if vacation_dates is None:
                vacation_dates = set()
            db_operating_hours = None
            day_schedule_hours: dict = {}
            try:
                from app.booking.operator_settings import (
                    get_vacation_days,
                    get_operating_hours,
                    get_day_schedule_hours_map,
                )
            except Exception as ie:
                logger.error("operator_settings import failed: %s", ie, exc_info=True)
            else:
                if need_vacation_fetch:
                    try:
                        vacation_dates = {
                            v["date"] for v in get_vacation_days(start_date.date(), end_date.date())
                        }
                    except Exception as e:
                        logger.warning("get_vacation_days failed (continuing): %s", e, exc_info=True)
                try:
                    db_operating_hours = get_operating_hours()   # 'HH:MM' (soporta media hora)
                except Exception as e:
                    logger.warning("get_operating_hours failed (continuing): %s", e, exc_info=True)
                try:
                    # Per-day custom hours from an assigned schedule-type profile
                    day_schedule_hours = get_day_schedule_hours_map(
                        start_date.date(), end_date.date()
                    )
                except Exception as e:
                    logger.warning("get_day_schedule_hours_map failed (continuing): %s", e, exc_info=True)

            # If settings failed to load, fall back to static config (hour ints)
            if db_operating_hours is None:
                db_operating_hours = list(self.config.operating_hours)

            # Group raw available slots by date
            by_date: dict = {}
            current_date = start_date.date()
            end_date_only = end_date.date()
            
            while current_date <= end_date_only:
                # Skip vacation days
                if str(current_date) in vacation_dates:
                    current_date += timedelta(days=1)
                    continue

                # A day with an assigned schedule-type profile uses its custom
                # hours; otherwise fall back to the global operating hours.
                hours_to_generate = day_schedule_hours.get(str(current_date)) or db_operating_hours
                if not hours_to_generate:
                    hours_to_generate = list(self.config.operating_hours)

                date_slots = self._generate_time_slots_for_date(
                    datetime.combine(current_date, time(0, 0)),
                    override_hours=hours_to_generate
                )
                
                for slot_datetime in date_slots:
                    # Skip if in the past
                    if slot_datetime < datetime.now(CHILE_TZ):
                        continue
                    
                    # Calculate slot range with buffer (duración del día del slot)
                    slot_start_with_buffer = slot_datetime - timedelta(hours=self.config.buffer_hours)
                    slot_end = slot_datetime + timedelta(hours=_dur_for(slot_datetime.date()))
                    slot_end_with_buffer = slot_end + timedelta(hours=self.config.buffer_hours)
                    
                    # Check if slot overlaps with any booked appointment (in-memory, fast)
                    # get_booked_slots already loaded booked rows from all_appointments,
                    # so no need for a second per-slot DB query (check_slot_availability).
                    overlaps = False
                    for booked_range in booked_ranges_by_date.get(slot_datetime.date(), []):
                        if (slot_start_with_buffer < booked_range['end'] and
                            slot_end_with_buffer > booked_range['start']):
                            overlaps = True
                            break
                    
                    if not overlaps:
                        slot_info = {
                            'datetime': slot_datetime,
                            'date': slot_datetime.date(),
                            'time': slot_datetime.strftime('%H:%M'),
                            'date_str': slot_datetime.strftime('%d/%m/%Y'),
                            'weekday': slot_datetime.strftime('%A')
                        }
                        dk = str(slot_datetime.date())
                        by_date.setdefault(dk, []).append(slot_info)
                
                current_date += timedelta(days=1)

            # Flatten back to list
            available_slots = [s for day_slots in by_date.values() for s in day_slots]
            available_slots.sort(key=lambda s: s["datetime"])
            
            return available_slots
            
        except Exception as e:
            logger.error(f"Error getting available slots: {e}")
            import traceback
            traceback.print_exc()
            return []

    async def _filter_to_web_bookable(self, slots: List[Dict]) -> List[Dict]:
        """Restrict raw slots to whatever the web booking page would actually
        show as bookable (green), so the bot never offers a time the customer
        can't actually pick on the site.

        Antes esto reimplementaba el filtro de modo urgencia llamando a
        apply_urgency_filter() directo — una función más simple que nunca
        recibió las correcciones iterativas (booked±gap, prioridad de
        ghost_times, restricción del listado del día, etc.) que sí se le
        hicieron a la lógica real del endpoint web
        (/api/booking/availability en router.py). Esas dos implementaciones
        se fueron desalineando con el tiempo. En vez de mantener una segunda
        copia de esa lógica, se llama directo a la función del endpoint web
        (misma fuente de verdad, con su propio cache de 30s).
        """
        try:
            from app.booking.router import get_availability as _web_get_availability
            web_data = await _web_get_availability(days=150)
            web_avail = web_data.get("availability", {})
            web_fake = web_data.get("fake_booked_slots", {})
            bookable_by_day = {
                dk: set(times) - set(web_fake.get(dk, []))
                for dk, times in web_avail.items()
            }
            return [
                s for s in slots
                if s["time"] in bookable_by_day.get(str(s["date"]), set())
            ]
        except Exception as _ue:
            logger.warning("Bot availability web-sync filter failed (continuing sin filtrar): %s", _ue, exc_info=True)
            return slots

    async def check_availability(self, message: str) -> str:
        """
        Check availability based on user query
        
        Args:
            message: User's message asking about availability
        
        Returns:
            Response with availability information
        """
        try:
            # Parse date from message if possible
            now = datetime.now(CHILE_TZ)
            current_year = now.year
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
            
            # Try to extract date keywords from message
            message_lower = message.lower()
            
            # First, try to parse a specific date (e.g., "14 de febrero")
            specific_date = self._parse_spanish_date(message, current_year)
            
            # Flag to track if this is a high-priority query (next 3 days)
            is_next_3_days = False
            
            if specific_date:
                # User asked for a specific date
                start_date = specific_date.replace(hour=0, minute=0, second=0, microsecond=0)
                end_date = specific_date.replace(hour=23, minute=59, second=59, microsecond=999999)
                days_to_show = 1
                specific_date_requested = True
                logger.info(f"Parsed specific date from message: {specific_date.date()}")
                
                # Check if the specific date is within next 3 days
                days_until_date = (specific_date - now).days
                if 0 <= days_until_date <= 3:
                    is_next_3_days = True
                    logger.info(f"🔴 High priority: Date within next 3 days ({days_until_date} days)")
            else:
                # Determine end date based on query
                specific_date_requested = False
                if "mañana" in message_lower or "tomorrow" in message_lower:
                    # User asked for tomorrow - set start_date to tomorrow, not today
                    tomorrow = now + timedelta(days=1)
                    start_date = tomorrow.replace(hour=0, minute=0, second=0, microsecond=0)
                    end_date = tomorrow.replace(hour=23, minute=59, second=59)
                    days_to_show = 1
                    is_next_3_days = True  # Tomorrow is within next 3 days
                    logger.info(f"User asked for tomorrow: {start_date.date()}")
                    logger.info("🔴 High priority: Tomorrow query")
                elif "próxima semana" in message_lower or "next week" in message_lower:
                    end_date = now + timedelta(days=7)
                    days_to_show = 7
                elif "mes" in message_lower or "month" in message_lower:
                    end_date = now + timedelta(days=30)
                    days_to_show = 30
                elif "hoy" in message_lower or "today" in message_lower:
                    # For "today", start from current time, not from midnight
                    start_date = now  # Start from NOW, not midnight
                    end_date = now.replace(hour=23, minute=59, second=59)
                    days_to_show = 1
                    specific_date_requested = True  # Treat "today" as specific date for better messaging
                    is_next_3_days = True  # Today is definitely within next 3 days
                    logger.info(f"User asked for today: {now.date()} starting from {now.strftime('%H:%M')}")
                    logger.info("🔴 High priority: Today query")
                else:
                    # Default: next 7 days
                    end_date = now + timedelta(days=7)
                    days_to_show = 7
                    # Check if default search overlaps with next 3 days
                    if days_to_show <= 3:
                        is_next_3_days = True
            
            # Auto-assign priority if querying for next 3 days
            if is_next_3_days and self.phone_number:
                await self._auto_set_priority_high(self.phone_number, "Consulta disponibilidad próximos 3 días")
            
            # Get available slots, restricted to what the web actually shows as bookable
            available_slots = await self.get_available_slots(start_date, end_date)
            available_slots = await self._filter_to_web_bookable(available_slots)

            logger.info(f"Found {len(available_slots)} available slots between {start_date.date()} and {end_date.date()}")
            
            if len(available_slots) == 0:
                # Check if user asked for "today" specifically
                if "hoy" in message_lower or "today" in message_lower:
                    return f"""❌ *Lo siento, no tenemos disponibilidad para hoy*

📅 Los horarios de hoy ({now.strftime('%d/%m/%Y')}) ya están ocupados o pasaron.

💡 *Te sugiero:*
• Consultar disponibilidad para *mañana*
• Ver disponibilidad para *esta semana*
• Visitar nuestro sitio: https://whatsapp.hotboat.cl/booking

¿Te gustaría que revise disponibilidad para mañana o esta semana? 🚤"""
                elif specific_date_requested:
                    if specific_date:
                        date_str = specific_date.strftime('%d de %B de %Y')
                    else:
                        date_str = now.strftime('%d de %B de %Y')
                    # Format month name in Spanish
                    month_names_es = {
                        'January': 'enero', 'February': 'febrero', 'March': 'marzo',
                        'April': 'abril', 'May': 'mayo', 'June': 'junio',
                        'July': 'julio', 'August': 'agosto', 'September': 'septiembre',
                        'October': 'octubre', 'November': 'noviembre', 'December': 'diciembre'
                    }
                    for en, es in month_names_es.items():
                        date_str = date_str.replace(en, es)
                    
                    return f"""❌ *Lo siento, no tenemos disponibilidad el {date_str}*

📅 Todos los horarios para esa fecha están ocupados.

💡 *Te sugiero:*
• Consultar disponibilidad para *otro día*
• Reservar con *anticipación*
• Visitar nuestro sitio: https://whatsapp.hotboat.cl/booking

¿Te gustaría que revise disponibilidad para otra fecha? 🚤"""
                else:
                    return """❌ *Lo siento, no tenemos disponibilidad en este momento*

📅 Para los próximos días todos los horarios están ocupados.

💡 *Te sugiero:*
• Consultar disponibilidad para la *próxima semana*
• Reservar con *anticipación*
• Visitar nuestro sitio: https://whatsapp.hotboat.cl/booking

¿Te gustaría que revise disponibilidad para otra fecha? 🚤"""
            
            # Group slots by date
            slots_by_date = {}
            for slot in available_slots:
                date_key = slot['date']
                if date_key not in slots_by_date:
                    slots_by_date[date_key] = []
                slots_by_date[date_key].append(slot)
            
            # Format response
            if "hoy" in message_lower or "today" in message_lower:
                # Special message for "today"
                response_parts = [f"✅ *¡Tenemos disponibilidad para HOY* ({now.strftime('%d/%m/%Y')})!\n"]
            elif specific_date_requested:
                if specific_date:
                    date_str = specific_date.strftime('%d de %B de %Y')
                else:
                    date_str = now.strftime('%d de %B de %Y')
                # Format month name in Spanish
                month_names_es = {
                    'January': 'enero', 'February': 'febrero', 'March': 'marzo',
                    'April': 'abril', 'May': 'mayo', 'June': 'junio',
                    'July': 'julio', 'August': 'agosto', 'September': 'septiembre',
                    'October': 'octubre', 'November': 'noviembre', 'December': 'diciembre'
                }
                for en, es in month_names_es.items():
                    date_str = date_str.replace(en, es)
                response_parts = [f"✅ *¡Tenemos disponibilidad el {date_str}!*\n"]
            else:
                response_parts = ["✅ *¡Tenemos disponibilidad!*\n"]
            
            # Show slots grouped by date
            date_count = 0
            # For "today" or specific dates, show only that date
            if "hoy" in message_lower or "today" in message_lower or specific_date_requested:
                max_dates_to_show = 1
            else:
                max_dates_to_show = 5 if days_to_show > 5 else days_to_show
            
            for date_key in sorted(slots_by_date.keys())[:max_dates_to_show]:
                slots = sorted(slots_by_date[date_key], key=lambda x: x['datetime'])
                first_slot = slots[0]
                
                # Format date in Spanish
                weekday_map = {
                    'Monday': 'Lunes',
                    'Tuesday': 'Martes',
                    'Wednesday': 'Miércoles',
                    'Thursday': 'Jueves',
                    'Friday': 'Viernes',
                    'Saturday': 'Sábado',
                    'Sunday': 'Domingo'
                }
                weekday_es = weekday_map.get(first_slot['weekday'], first_slot['weekday'])
                
                time_str = ", ".join([s['time'] for s in slots])
                response_parts.append(
                    f"📅 *{weekday_es} {first_slot['date_str']}*: {time_str}"
                )
                date_count += 1
            
            if len(slots_by_date) > max_dates_to_show:
                remaining = len(slots_by_date) - max_dates_to_show
                response_parts.append(f"\n... y {remaining} día(s) más con disponibilidad")
            
            response_parts.append("\n🛒 *¿Cómo reservo?*")
            response_parts.append("Solo dime la *fecha*, *hora* y *número de personas*.")
            response_parts.append("\nPor ejemplo:")
            response_parts.append("• *\"El martes a las 16 para 3 personas\"*")
            response_parts.append("• *\"4 de noviembre a las 15 para 2 personas\"*")
            response_parts.append("\nYo lo agrego al carrito automáticamente 🚤")
            response_parts.append("\n💡 También puedes reservar directamente aquí:")
            response_parts.append("https://whatsapp.hotboat.cl/booking")
            
            return "\n".join(response_parts)
            
        except Exception as e:
            logger.error(f"Error checking availability: {e}")
            import traceback
            traceback.print_exc()
            return "Disculpa, tuve un problema consultando la disponibilidad. Te responderé en un momento. Gracias por tu paciencia 🙏"
