-- When the booking confirmation email was sent (idempotent webhook / retries)
ALTER TABLE hotboat_appointments
ADD COLUMN IF NOT EXISTS confirmation_email_sent_at TIMESTAMPTZ;
rificado en Resend, p. ej. Reservas HotBoat <noreply@reservas.hotboat.cl> (o la dirección exacta que te dieron para reservas.hotboat.cl).
RESEND_BCC_BOOKING	(Opcional) Tu correo para recibir copia en BCC, separado por comas si son varios.
Si no defines RESEND_FROM_CONFIRMATIONS, se usa EMAIL_FROM (debe ser un dominio/remitente válido en Resend).

3. Panel admin (opcional)
En Emails reservas: deja activado “Enviar email de confirmación” y “al confirmarse el pago”, o ajusta asunto/HTML. Con Enviar prueba compruebas que Resend y el remitente estén bien antes de un pago real.

4. Flujo real
El correo se manda cuando la reserva web queda confirmed y el cliente tiene email, típicamente al confirmar el pago en WooCommerce (webhook que ya actualiza hotboat_appointments). Asegúrate de que el webhook siga apuntando a tu app y que Woo envíe el pedido pagado como hasta ahora.

Resumen: migración aplicada + RESEND_API_KEY + remitente verificado (RESEND_FROM_CONFIRMATIONS o EMAIL_FROM) + probar con “Enviar prueba” en el admin.