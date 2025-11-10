# Configuración de Resend para Emails en Railway

## ¿Por qué Resend?

Railway y la mayoría de plataformas PaaS bloquean el tráfico SMTP saliente (puertos 25, 465, 587) por seguridad. Por eso usamos **Resend**, un servicio de email que funciona mediante API HTTPS, sin restricciones.

## Pasos para Configurar Resend

### 1. Crear cuenta en Resend

1. Ve a [https://resend.com/signup](https://resend.com/signup)
2. Crea una cuenta gratuita (incluye 3,000 emails/mes gratis)
3. Confirma tu email

### 2. Obtener API Key

1. Entra al dashboard: [https://resend.com/api-keys](https://resend.com/api-keys)
2. Click en "Create API Key"
3. Dale un nombre (ej: "HotBoat Production")
4. **Copia la API key** (empieza con `re_`) - solo la verás una vez

### 3. Configurar dominio (Opcional pero recomendado)

**Opción A - Dominio propio (recomendado):**
1. Ve a [https://resend.com/domains](https://resend.com/domains)
2. Click en "Add Domain"
3. Ingresa tu dominio (ej: `hotboatchile.com`)
4. Agrega los registros DNS que te indica Resend en tu proveedor de dominio
5. Una vez verificado, podrás enviar desde `notificaciones@hotboatchile.com`

**Opción B - Dominio de prueba (solo para testing):**
- Usa `onboarding@resend.dev` (viene incluido)
- Tiene limitaciones: solo puedes enviar a emails que agregues manualmente en Resend

### 4. Configurar variables en Railway

1. Ve a tu proyecto en Railway
2. Click en tu servicio (el bot de WhatsApp)
3. Ve a la pestaña "Variables"
4. Agrega/actualiza estas variables:

```
EMAIL_ENABLED=true
RESEND_API_KEY=re_tu_api_key_aqui
EMAIL_FROM=notificaciones@hotboatchile.com
NOTIFICATION_EMAILS=tu-email@gmail.com,otro@email.com
```

**Notas importantes:**
- Si usas dominio propio: `EMAIL_FROM=notificaciones@hotboatchile.com`
- Si usas dominio de prueba: `EMAIL_FROM=onboarding@resend.dev`
- `NOTIFICATION_EMAILS` puede tener múltiples emails separados por coma

### 5. Desplegar cambios

1. Railway detectará automáticamente los cambios en el código
2. O ejecuta manualmente:
   ```bash
   git add .
   git commit -m "Migrar a Resend para emails"
   git push
   ```

### 6. Verificar funcionamiento

1. Haz una reserva de prueba o solicita "ayuda" en WhatsApp
2. Verifica que llegue el email a las direcciones configuradas
3. Revisa los logs en Railway para confirmar:
   ```
   Email notification sent via Resend: Nueva reserva confirmada...
   ```

## Troubleshooting

### Error: "Resend library not installed"
```bash
pip install resend
```

### Error: "RESEND_API_KEY not configured"
Verifica que la variable esté configurada en Railway y que empiece con `re_`

### Error: "Email not verified"
Si usas dominio propio, verifica que los registros DNS estén correctos en Resend dashboard

### Los emails van a spam
1. Configura SPF/DKIM en tu dominio (Resend te da las instrucciones)
2. Agrega `noreply@` o `notificaciones@` en lugar de direcciones genéricas

## Precios

- **Plan gratuito:** 3,000 emails/mes, 100 emails/día
- **Plan Pro:** $20/mes por 50,000 emails/mes
- Para HotBoat, el plan gratuito es más que suficiente

## Links útiles

- Dashboard: [https://resend.com/dashboard](https://resend.com/dashboard)
- Documentación: [https://resend.com/docs](https://resend.com/docs)
- Estado del servicio: [https://resend.com/status](https://resend.com/status)

