# ⚡ Quick Start - HotBoat WhatsApp Bot

Guía rápida para poner el bot en funcionamiento en **15 minutos**.

---

## 📋 Checklist

### 1. Obtener credenciales necesarias ✅

- [ ] **Groq API Key (GRATIS!)**: https://console.groq.com/
  - Crea cuenta (gratis, sin tarjeta)
  - Ve a API Keys → Create API Key
  - Copia el key: `gsk_...`

- [ ] **WhatsApp Business API**:
  - Ve a tu configuración en Meta (ya lo tienes)
  - Copia: API Token, Phone Number ID, Business Account ID

- [ ] **DATABASE_URL**:
  - Usa el mismo de `hotboat-etl` en Railway
  - Formato: `postgresql://user:pass@host:port/dbname`

### 2. Crear repositorio GitHub ✅

```bash
# En tu carpeta hotboat-whatsapp
git init
git add .
git commit -m "Initial commit - HotBoat WhatsApp Bot"

# Crea repo en GitHub y luego:
git remote add origin https://github.com/TU-USUARIO/hotboat-whatsapp.git
git push -u origin main
```

### 3. Deploy en Railway ✅

1. **Ve a Railway**: https://railway.app
2. **New Project** → **Deploy from GitHub repo**
3. Selecciona `hotboat-whatsapp`
4. Railway detecta FastAPI automáticamente ✅

### 4. Configurar variables en Railway ✅

En Railway → tu proyecto → **Variables**, agrega:

```env
DATABASE_URL=postgresql://postgres:xxxxx@xxxx.railway.app:5432/railway
WHATSAPP_API_TOKEN=EAAxxxxx
WHATSAPP_PHONE_NUMBER_ID=123456789
WHATSAPP_BUSINESS_ACCOUNT_ID=987654321
WHATSAPP_VERIFY_TOKEN=MiTokenSecreto123
GROQ_API_KEY=gsk_xxxxx
PORT=8000
```

### 5. Obtener URL de Railway ✅

Railway te dará una URL como:
```
https://hotboat-whatsapp-production.up.railway.app
```

### 6. Configurar Webhook en Meta ✅

1. Ve a: https://developers.facebook.com/ → Tu App → WhatsApp
2. **Webhook**:
   - URL: `https://tu-app.railway.app/webhook`
   - Verify Token: (el mismo que pusiste en `WHATSAPP_VERIFY_TOKEN`)
3. **Subscribe to**: `messages`
4. Click **Verify and Save**

### 7. ¡Probar! ✅

Envía un mensaje de WhatsApp a tu número:

```
"Hola"
```

Deberías recibir una respuesta del bot 🎉

---

## 🧪 Test Rápido

### Test 1: Health Check
```bash
curl https://tu-app.railway.app/health
```

Respuesta esperada:
```json
{"status":"healthy","database":"connected","whatsapp_api":"configured"}
```

### Test 2: FAQ
Envía por WhatsApp:
```
"¿Cuánto cuesta?"
```

Deberías recibir los precios.

### Test 3: Disponibilidad
Envía por WhatsApp:
```
"¿Tienen disponibilidad para mañana?"
```

El bot consultará y responderá.

### Test 4: IA General
Envía por WhatsApp:
```
"Cuéntame sobre el tour"
```

Groq AI generará una respuesta personalizada (gratis!).

---

## 🐛 Troubleshooting

### El bot no responde

1. **Check logs en Railway**:
   - Ve a Deployments → Deploy Logs
   - Busca errores

2. **Verifica variables**:
   - Todas las variables están configuradas?
   - Los tokens son correctos?

3. **Check webhook**:
   - En Meta → WhatsApp → Configuration
   - El webhook está verificado? ✅

### Error de base de datos

```
Error: connection refused
```

**Solución**: Asegúrate que `DATABASE_URL` sea la correcta de Railway PostgreSQL.

### Error de Groq

```
Error: Invalid API key
```

**Solución**: Verifica tu `GROQ_API_KEY` en https://console.groq.com/

---

## 🎉 ¡Listo!

Tu bot ya está funcionando. Ahora puedes:

1. ✅ Probar todas las funciones
2. ✅ Personalizar las respuestas en `app/bot/faq.py`
3. ✅ Ajustar el prompt de IA en `app/bot/ai_handler.py`
4. ✅ Ver conversaciones en los logs de Railway

---

## 📞 ¿Problemas?

Revisa el README completo o los logs de Railway para más detalles.



