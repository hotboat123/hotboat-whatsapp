"""
Availability checker - queries PostgreSQL for appointment availability
"""
import logging
import re
from datetime import datetime, timedelta, time
from typing import Optional, List, Dict, Tuple
import pytz

from app.db.queries import get_booked_slots, check_slot_availability
from app.availability.availability_config import (
    AVAILABILITY_CONFIG,
    get_service_config
)

logger = logging.getLogger(__name__)

# Timezone for Chile
CHILE_TZ = pytz.timezone('America/Santiago')

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
                parsed_date = CHILE_TZ.localize(parsed_date_naive)
                # Only move to next year if the whole calendar day is in the past, not just the time.
                if parsed_date.date() < now.date():
                    parsed_date_naive = datetime(current_year + 1, month, day, 0, 0, 0)
                    parsed_date = CHILE_TZ.localize(parsed_date_naive)
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
        return await self.get_available_slots(start_date, end_date)
    
    def _generate_time_slots_for_date(self, date: datetime) -> List[datetime]:
        """Generate all possible time slots for a given date"""
        slots = []
        date_obj = date.date() if isinstance(date, datetime) else date
        for hour in self.config.operating_hours:
            dt_naive = datetime.combine(date_obj, time(hour, 0))
            slot = CHILE_TZ.localize(dt_naive)
            slots.append(slot)
        return slots
    
    async def get_available_slots(
        self,
        start_date: datetime,
        end_date: datetime,
        party_size: Optional[int] = None
    ) -> List[Dict]:
        """
        Get available time slots from database
        
        Args:
            start_date: Start date for search
            end_date: End date for search
            party_size: Number of people (optional)
        
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
            
            # Create a set of booked time ranges for overlap checking
            # Store (date, start_hour, end_hour) for each appointment
            booked_ranges = []
            for slot in booked_slots:
                if slot['starts_at']:
                    dt = slot['starts_at']
                    if isinstance(dt, str):
                        dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
                    
                    # Calculate appointment range with buffer
                    appointment_start = dt
                    appointment_duration = self.config.duration_hours
                    appointment_end = appointment_start + timedelta(hours=appointment_duration)
                    
                    # Apply buffer
                    appointment_start_with_buffer = appointment_start - timedelta(hours=self.config.buffer_hours)
                    appointment_end_with_buffer = appointment_end + timedelta(hours=self.config.buffer_hours)
                    
                    booked_ranges.append({
                        'start': appointment_start_with_buffer,
                        'end': appointment_end_with_buffer,
                        'date': dt.date()
                    })
            
            # Generate all possible slots and check availability
            available_slots = []
            current_date = start_date.date()
            end_date_only = end_date.date()
            
            while current_date <= end_date_only:
                date_slots = self._generate_time_slots_for_date(
                    datetime.combine(current_date, time(0, 0))
                )
                
                for slot_datetime in date_slots:
                    # Skip if in the past
                    if slot_datetime < datetime.now(CHILE_TZ):
                        continue
                    
                    # Calculate slot range with buffer
                    slot_start_with_buffer = slot_datetime - timedelta(hours=self.config.buffer_hours)
                    slot_end = slot_datetime + timedelta(hours=self.config.duration_hours)
                    slot_end_with_buffer = slot_end + timedelta(hours=self.config.buffer_hours)
                    
                    # Check if slot overlaps with any booked appointment
                    overlaps = False
                    for booked_range in booked_ranges:
                        # Only check appointments on the same date
                        if booked_range['date'] != slot_datetime.date():
                            continue
                        
                        # Check for overlap: slot overlaps if it starts before appointment ends
                        # AND slot ends after appointment starts
                        if (slot_start_with_buffer < booked_range['end'] and 
                            slot_end_with_buffer > booked_range['start']):
                            overlaps = True
                            break
                    
                    if not overlaps:
                        # Double check with database query for accuracy
                        is_available = await check_slot_availability(
                            slot_datetime,
                            duration_hours=self.config.duration_hours,
                            buffer_hours=self.config.buffer_hours
                        )
                        
                        if is_available:
                            available_slots.append({
                                'datetime': slot_datetime,
                                'date': slot_datetime.date(),
                                'time': slot_datetime.strftime('%H:%M'),
                                'date_str': slot_datetime.strftime('%d/%m/%Y'),
                                'weekday': slot_datetime.strftime('%A')
                            })
                
                current_date += timedelta(days=1)
            
            return available_slots
            
        except Exception as e:
            logger.error(f"Error getting available slots: {e}")
            import traceback
            traceback.print_exc()
            return []
    
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
            
            if specific_date:
                # User asked for a specific date
                start_date = specific_date.replace(hour=0, minute=0, second=0, microsecond=0)
                end_date = specific_date.replace(hour=23, minute=59, second=59, microsecond=999999)
                days_to_show = 1
                specific_date_requested = True
                logger.info(f"Parsed specific date from message: {specific_date.date()}")
            else:
                # Determine end date based on query
                specific_date_requested = False
                if "mañana" in message_lower or "tomorrow" in message_lower:
                    # User asked for tomorrow - set start_date to tomorrow, not today
                    tomorrow = now + timedelta(days=1)
                    start_date = tomorrow.replace(hour=0, minute=0, second=0, microsecond=0)
                    end_date = tomorrow.replace(hour=23, minute=59, second=59)
                    days_to_show = 1
                    logger.info(f"User asked for tomorrow: {start_date.date()}")
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
                    logger.info(f"User asked for today: {now.date()} starting from {now.strftime('%H:%M')}")
                else:
                    # Default: next 7 days
                    end_date = now + timedelta(days=7)
                    days_to_show = 7
            
            # Get available slots
            available_slots = await self.get_available_slots(start_date, end_date)
            
            logger.info(f"Found {len(available_slots)} available slots between {start_date.date()} and {end_date.date()}")
            
            if len(available_slots) == 0:
                # Check if user asked for "today" specifically
                if "hoy" in message_lower or "today" in message_lower:
                    return f"""❌ *Lo siento, no tenemos disponibilidad para hoy*

📅 Los horarios de hoy ({now.strftime('%d/%m/%Y')}) ya están ocupados o pasaron.

💡 *Te sugiero:*
• Consultar disponibilidad para *mañana*
• Ver disponibilidad para *esta semana*
• Visitar nuestro sitio: https://hotboatchile.com/es/book-hotboat/

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
• Visitar nuestro sitio: https://hotboatchile.com/es/book-hotboat/

¿Te gustaría que revise disponibilidad para otra fecha? 🚤"""
                else:
                    return """❌ *Lo siento, no tenemos disponibilidad en este momento*

📅 Para los próximos días todos los horarios están ocupados.

💡 *Te sugiero:*
• Consultar disponibilidad para la *próxima semana*
• Reservar con *anticipación*
• Visitar nuestro sitio: https://hotboatchile.com/es/book-hotboat/

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
            response_parts.append("https://hotboatchile.com/es/book-hotboat/")
            
            return "\n".join(response_parts)
            
        except Exception as e:
            logger.error(f"Error checking availability: {e}")
            import traceback
            traceback.print_exc()
            return "Disculpa, tuve un problema consultando la disponibilidad. Te responderé en un momento. Gracias por tu paciencia 🙏"








