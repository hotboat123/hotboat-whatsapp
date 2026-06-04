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
        """Obtiene el estado actual de las reservas desde ``all_appointments``."""
        # Reservas activas desde la tabla canónica ``all_appointments``
        query = """
            SELECT
                id::text AS id,
                nombre_cliente AS customer_name,
                COALESCE(email, '') AS customer_email,
                COALESCE(telefono, '') AS customer_phone,
                COALESCE(servicio, '') AS service_name,
                (fecha + hora) AT TIME ZONE 'America/Santiago' AS starts_at,
                120 AS duration,
                status,
                COALESCE(ingreso_total, 0)::float AS price,
                CASE
                    WHEN payment_status = 'approved' OR status = 'confirmed'
                    THEN COALESCE(ingreso_total, 0)::float
                    ELSE 0::float
                END AS paid_amount,
                created_at,
                COALESCE(observaciones, '') AS note,
                extras_json AS custom_fields
            FROM all_appointments
            WHERE hora IS NOT NULL
              AND (fecha + hora) AT TIME ZONE 'America/Santiago'
                  >= CURRENT_TIMESTAMP - INTERVAL '1 day'
              AND (status IS NULL OR status NOT IN ('cancelled', 'rejected', 'cancelada'))
            ORDER BY fecha, hora
        """

        try:
            appointments = await execute_query(query)
        except Exception as e:
            logger.warning(f"⚠️ Error al consultar all_appointments (monitor): {e}")
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
            'customer_name', 'customer_phone', 'customer_email',
            'starts_at', 'duration', 'service_name',
            'price', 'paid_amount', 'status', 'note'
        ]
        
        for field in fields:
            if old_appt.get(field) != new_appt.get(field):
                return True
        
        return False
    
    async def _notify_new_appointment(self, appointment: Dict):
        """Notifica sobre una nueva reserva de Booknetic"""
        if not self.config.get("notifications", {}).get("new_appointment", True):
            return
        
        # Formatear fecha y hora
        starts_at = appointment.get('starts_at')
        if starts_at:
            if isinstance(starts_at, str):
                from datetime import datetime
                starts_at = datetime.fromisoformat(starts_at.replace('Z', '+00:00'))
            date_str = starts_at.strftime('%d/%m/%Y')
            time_str = starts_at.strftime('%H:%M')
        else:
            date_str = 'N/A'
            time_str = 'N/A'
        
        # Parsear custom_fields si existe (puede contener info de personas y extras)
        custom_fields = appointment.get('custom_fields')
        num_people = 'N/A'
        extras_info = ''
        
        if custom_fields:
            try:
                import json
                if isinstance(custom_fields, str):
                    fields = json.loads(custom_fields)
                else:
                    fields = custom_fields
                
                # Buscar número de personas (puede estar en diferentes campos)
                for key, value in fields.items():
                    if 'persona' in key.lower() or 'people' in key.lower() or 'capacity' in key.lower():
                        num_people = value
                        break
                
                # Buscar extras
                extras_list = []
                for key, value in fields.items():
                    if 'extra' in key.lower() or 'addon' in key.lower() or 'servicio' in key.lower():
                        if value and value != 'none' and value != '':
                            extras_list.append(f"• {key}: {value}")
                
                if extras_list:
                    extras_info = "\n\n✨ *Extras:*\n" + "\n".join(extras_list)
            except:
                pass
        
        # Construir mensaje
        price = appointment.get('price', 0)
        paid_amount = appointment.get('paid_amount', 0)
        pendiente_line = (
            f"⚠️ *Pendiente:* ${price - paid_amount:,.0f} CLP"
            if price > paid_amount else "✅ *Pagado completamente*"
        )
        note_line = ""
        if appointment.get("note"):
            note_line = "\n📝 *Notas:* " + str(appointment.get("note"))

        message = f"""🎉 *NUEVA RESERVA HOTBOAT*

👤 *Cliente:* {appointment.get('customer_name', 'N/A')}
📱 *Teléfono:* {appointment.get('customer_phone', 'N/A')}
📧 *Email:* {appointment.get('customer_email', 'N/A')}

📅 *Fecha:* {date_str}
⏰ *Hora:* {time_str}
⏱️ *Duración:* {appointment.get('duration', 'N/A')} min
⛵ *Servicio:* {appointment.get('service_name', 'N/A')}
👥 *Personas:* {num_people}

💰 *Precio total:* ${price:,.0f} CLP
💳 *Monto pagado:* ${paid_amount:,.0f} CLP
{pendiente_line}
{extras_info}
{note_line}

🔗 *ID Reserva:* #{appointment.get('id')}
        """.strip()
        
        await self.send_notification(
            message=message,
            priority="high"
        )
        
        logger.info(f"🎉 Nueva reserva: {appointment.get('customer_name')} - {date_str} {time_str}")
    
    async def _notify_cancelled_appointment(self, appointment: Dict):
        """Notifica sobre una reserva cancelada"""
        if not self.config.get("notifications", {}).get("cancelled_appointment", True):
            return
        
        # Formatear fecha y hora
        starts_at = appointment.get('starts_at')
        if starts_at:
            if isinstance(starts_at, str):
                from datetime import datetime
                starts_at = datetime.fromisoformat(starts_at.replace('Z', '+00:00'))
            date_str = starts_at.strftime('%d/%m/%Y')
            time_str = starts_at.strftime('%H:%M')
        else:
            date_str = 'N/A'
            time_str = 'N/A'
        
        message = f"""❌ *Reserva Cancelada*

👤 Cliente: {appointment.get('customer_name', 'N/A')}
📱 Teléfono: {appointment.get('customer_phone', 'N/A')}
📅 Fecha: {date_str}
⏰ Hora: {time_str}
💰 Monto: ${appointment.get('price', 0):,.0f} CLP

🔗 *ID Reserva:* #{appointment.get('id')}
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
        
        # Comparar fechas/hora
        old_starts = old_appt.get('starts_at')
        new_starts = new_appt.get('starts_at')
        if old_starts != new_starts:
            from datetime import datetime
            if isinstance(old_starts, str):
                old_starts = datetime.fromisoformat(old_starts.replace('Z', '+00:00'))
            if isinstance(new_starts, str):
                new_starts = datetime.fromisoformat(new_starts.replace('Z', '+00:00'))
            
            if old_starts and new_starts:
                old_str = old_starts.strftime('%d/%m/%Y %H:%M')
                new_str = new_starts.strftime('%d/%m/%Y %H:%M')
                changes.append(f"📅 Fecha/Hora: {old_str} → {new_str}")
        
        if old_appt.get('price') != new_appt.get('price'):
            changes.append(f"💰 Precio: ${old_appt.get('price', 0):,.0f} → ${new_appt.get('price', 0):,.0f}")
        
        if old_appt.get('paid_amount') != new_appt.get('paid_amount'):
            changes.append(f"💳 Pagado: ${old_appt.get('paid_amount', 0):,.0f} → ${new_appt.get('paid_amount', 0):,.0f}")
        
        if old_appt.get('status') != new_appt.get('status'):
            changes.append(f"📝 Estado: {old_appt.get('status')} → {new_appt.get('status')}")
        
        if old_appt.get('duration') != new_appt.get('duration'):
            changes.append(f"⏱️ Duración: {old_appt.get('duration')} → {new_appt.get('duration')} min")
        
        if not changes:
            return
        
        message = f"""🔄 *Reserva Modificada*

👤 Cliente: {new_appt.get('customer_name', 'N/A')}
📱 Teléfono: {new_appt.get('customer_phone', 'N/A')}

*Cambios:*
{chr(10).join(changes)}

🔗 *ID Reserva:* #{new_appt.get('id')}
        """.strip()
        
        await self.send_notification(
            message=message,
            priority="medium"
        )
        
        logger.info(f"🔄 Reserva modificada: {new_appt.get('customer_name')}")

