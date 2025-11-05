"""
Monitor de Appointments (Reservas)
"""
from typing import Dict, Any, Set
from datetime import datetime, timedelta
import pytz

from automations.monitors.base_monitor import BaseMonitor
from automations.database import execute_query
from app.utils.logger import logger


class AppointmentsMonitor(BaseMonitor):
    """Monitorea cambios en las reservas"""
    
    async def check(self) -> Dict[str, Any]:
        """
        Obtiene el estado actual de las reservas
        """
        # Obtener todas las reservas activas (próximas y recientes)
        query = """
            SELECT 
                id,
                customer_name,
                phone_number,
                appointment_date,
                start_time,
                duration_hours,
                boat_type,
                num_people,
                total_price,
                status,
                created_at,
                updated_at,
                notes
            FROM appointments
            WHERE appointment_date >= CURRENT_DATE - INTERVAL '1 day'
            ORDER BY appointment_date, start_time
        """
        
        try:
            appointments = await execute_query(query)
        except Exception as e:
            logger.warning(f"⚠️ Error al consultar appointments: {e}")
            return {}
        
        # Crear un diccionario indexado por ID para fácil comparación
        appointments_dict = {
            str(appt['id']): appt for appt in appointments
        }
        
        logger.debug(f"📅 {len(appointments)} reservas activas encontradas")
        
        return appointments_dict
    
    async def detect_changes(self, current_state: Dict[str, Any]) -> None:
        """
        Detecta cambios en las reservas y envía notificaciones
        """
        if self.last_state is None:
            return
        
        last_ids: Set[str] = set(self.last_state.keys())
        current_ids: Set[str] = set(current_state.keys())
        
        # Nuevas reservas
        new_ids = current_ids - last_ids
        for appt_id in new_ids:
            await self._notify_new_appointment(current_state[appt_id])
        
        # Reservas eliminadas/canceladas
        deleted_ids = last_ids - current_ids
        for appt_id in deleted_ids:
            await self._notify_cancelled_appointment(self.last_state[appt_id])
        
        # Reservas modificadas
        common_ids = last_ids & current_ids
        for appt_id in common_ids:
            last_appt = self.last_state[appt_id]
            current_appt = current_state[appt_id]
            
            if self._has_changed(last_appt, current_appt):
                await self._notify_modified_appointment(last_appt, current_appt)
    
    def _has_changed(self, old_appt: Dict, new_appt: Dict) -> bool:
        """Verifica si una reserva ha cambiado"""
        fields = [
            'customer_name', 'phone_number', 'appointment_date',
            'start_time', 'duration_hours', 'boat_type',
            'num_people', 'total_price', 'status'
        ]
        
        for field in fields:
            if old_appt.get(field) != new_appt.get(field):
                return True
        
        return False
    
    async def _notify_new_appointment(self, appointment: Dict):
        """Notifica sobre una nueva reserva"""
        if not self.config.get("notifications", {}).get("new_appointment", True):
            return
        
        date_str = appointment['appointment_date'].strftime('%d/%m/%Y')
        time_str = str(appointment.get('start_time', 'N/A'))
        
        message = f"""🎉 *Nueva Reserva Creada*

👤 Cliente: {appointment.get('customer_name', 'N/A')}
📱 Teléfono: {appointment.get('phone_number', 'N/A')}
📅 Fecha: {date_str}
⏰ Hora: {time_str}
⛵ Embarcación: {appointment.get('boat_type', 'N/A')}
👥 Personas: {appointment.get('num_people', 'N/A')}
💰 Total: ${appointment.get('total_price', 0):,.0f}
📝 Estado: {appointment.get('status', 'N/A')}

{f"Notas: {appointment.get('notes')}" if appointment.get('notes') else ""}
        """.strip()
        
        await self.send_notification(
            message=message,
            priority="high"
        )
        
        logger.info(f"🎉 Nueva reserva: {appointment.get('customer_name')} - {date_str}")
    
    async def _notify_cancelled_appointment(self, appointment: Dict):
        """Notifica sobre una reserva cancelada"""
        if not self.config.get("notifications", {}).get("cancelled_appointment", True):
            return
        
        date_str = appointment['appointment_date'].strftime('%d/%m/%Y')
        
        message = f"""❌ *Reserva Cancelada*

👤 Cliente: {appointment.get('customer_name', 'N/A')}
📅 Fecha: {date_str}
⏰ Hora: {appointment.get('start_time', 'N/A')}
💰 Monto: ${appointment.get('total_price', 0):,.0f}
        """.strip()
        
        await self.send_notification(
            message=message,
            priority="medium"
        )
        
        logger.info(f"❌ Reserva cancelada: {appointment.get('customer_name')} - {date_str}")
    
    async def _notify_modified_appointment(self, old_appt: Dict, new_appt: Dict):
        """Notifica sobre cambios en una reserva"""
        if not self.config.get("notifications", {}).get("modified_appointment", True):
            return
        
        # Detectar qué cambió
        changes = []
        
        if old_appt.get('appointment_date') != new_appt.get('appointment_date'):
            old_date = old_appt['appointment_date'].strftime('%d/%m/%Y')
            new_date = new_appt['appointment_date'].strftime('%d/%m/%Y')
            changes.append(f"📅 Fecha: {old_date} → {new_date}")
        
        if old_appt.get('start_time') != new_appt.get('start_time'):
            changes.append(f"⏰ Hora: {old_appt.get('start_time')} → {new_appt.get('start_time')}")
        
        if old_appt.get('status') != new_appt.get('status'):
            changes.append(f"📝 Estado: {old_appt.get('status')} → {new_appt.get('status')}")
        
        if old_appt.get('num_people') != new_appt.get('num_people'):
            changes.append(f"👥 Personas: {old_appt.get('num_people')} → {new_appt.get('num_people')}")
        
        if not changes:
            return
        
        message = f"""🔄 *Reserva Modificada*

👤 Cliente: {new_appt.get('customer_name', 'N/A')}
📱 Teléfono: {new_appt.get('phone_number', 'N/A')}

*Cambios:*
{chr(10).join(changes)}
        """.strip()
        
        await self.send_notification(
            message=message,
            priority="medium"
        )
        
        logger.info(f"🔄 Reserva modificada: {new_appt.get('customer_name')}")

