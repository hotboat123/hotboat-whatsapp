"""
Availability checker - queries PostgreSQL for appointment availability
"""
import logging
from datetime import datetime, timedelta, time
from typing import Optional, List, Dict
import pytz

from app.db.queries import get_booked_slots, check_slot_availability
from app.availability.availability_config import (
    AVAILABILITY_CONFIG,
    get_service_config
)

logger = logging.getLogger(__name__)

# Timezone for Chile
CHILE_TZ = pytz.timezone('America/Santiago')


class AvailabilityChecker:
    """Check availability by querying appointments database"""
    
    def __init__(self):
        self.config = AVAILABILITY_CONFIG
    
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
            
            # Create a set of booked datetimes for quick lookup
            booked_times = set()
            for slot in booked_slots:
                if slot['starts_at']:
                    # Normalize to hour (remove minutes/seconds)
                    dt = slot['starts_at']
                    if isinstance(dt, str):
                        dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
                    # Round to nearest operating hour
                    hour = dt.hour
                    if hour in self.config.operating_hours:
                        booked_times.add((dt.date(), hour))
            
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
                    
                    # Check if this slot is booked
                    slot_key = (slot_datetime.date(), slot_datetime.hour)
                    if slot_key not in booked_times:
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
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
            
            # Try to extract date keywords from message
            message_lower = message.lower()
            
            # Determine end date based on query
            if "mañana" in message_lower or "tomorrow" in message_lower:
                end_date = (now + timedelta(days=1)).replace(hour=23, minute=59, second=59)
                days_to_show = 1
            elif "próxima semana" in message_lower or "next week" in message_lower:
                end_date = now + timedelta(days=7)
                days_to_show = 7
            elif "mes" in message_lower or "month" in message_lower:
                end_date = now + timedelta(days=30)
                days_to_show = 30
            elif "hoy" in message_lower or "today" in message_lower:
                end_date = now.replace(hour=23, minute=59, second=59)
                days_to_show = 1
            else:
                # Default: next 7 days
                end_date = now + timedelta(days=7)
                days_to_show = 7
            
            # Get available slots
            available_slots = await self.get_available_slots(start_date, end_date)
            
            logger.info(f"Found {len(available_slots)} available slots between {start_date.date()} and {end_date.date()}")
            
            if len(available_slots) == 0:
                return """❌ **Lo siento, no tenemos disponibilidad en este momento**

📅 Para los próximos días todos los horarios están ocupados.

💡 Te sugiero:
• Consultar disponibilidad para la próxima semana
• Reservar con anticipación
• Visitar nuestro sitio: https://hotboatchile.com/es/book-hotboat/

¿Te gustaría que revise disponibilidad para otra fecha?"""
            
            # Group slots by date
            slots_by_date = {}
            for slot in available_slots:
                date_key = slot['date']
                if date_key not in slots_by_date:
                    slots_by_date[date_key] = []
                slots_by_date[date_key].append(slot)
            
            # Format response
            response_parts = ["✅ **¡Tenemos disponibilidad!**\n"]
            
            # Show slots grouped by date
            date_count = 0
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
                    f"📅 **{weekday_es} {first_slot['date_str']}**: {time_str}"
                )
                date_count += 1
            
            if len(slots_by_date) > max_dates_to_show:
                remaining = len(slots_by_date) - max_dates_to_show
                response_parts.append(f"\n... y {remaining} día(s) más con disponibilidad")
            
            response_parts.append("\n👥 **¿Para cuántas personas sería?**")
            response_parts.append("Puedo ayudarte a reservar el horario perfecto.")
            response_parts.append("\n💡 También puedes reservar directamente aquí:")
            response_parts.append("https://hotboatchile.com/es/book-hotboat/")
            
            return "\n".join(response_parts)
            
        except Exception as e:
            logger.error(f"Error checking availability: {e}")
            import traceback
            traceback.print_exc()
            return "Disculpa, tuve un problema consultando la disponibilidad. Te responderé en un momento. Gracias por tu paciencia 🙏"



