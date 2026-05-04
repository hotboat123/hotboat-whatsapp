# 🧪 Cómo Probar el Sistema de Disponibilidad en WhatsApp

## ✅ Verificación previa

Antes de probar en WhatsApp, asegúrate de que:

1. **Base de datos configurada** ✅
   - DATABASE_URL está configurado en Railway o en tu archivo `.env`
   - La conexión funciona correctamente

2. **Variables de entorno configuradas**:
   ```env
   DATABASE_URL=postgresql://postgres:...@turntable.proxy.rlwy.net:48129/railway
   WHATSAPP_API_TOKEN=tu_token_aqui
   WHATSAPP_PHONE_NUMBER_ID=tu_phone_id
   WHATSAPP_BUSINESS_ACCOUNT_ID=tu_account_id
   WHATSAPP_VERIFY_TOKEN=tu_token_personalizado
   GROQ_API_KEY=tu_api_key
   ```

## 🚀 Pasos para probar

### 1. Instalar dependencias (si no lo has hecho)

```bash
pip install -r requirements.txt
```

### 2. Iniciar el servidor

```bash
python -m uvicorn app.main:app --reload --port 8000
```

O si estás en Railway, el servidor debería iniciarse automáticamente.

Deberías ver algo como:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete.
```

### 3. Verificar que el servidor está funcionando

Abre en tu navegador:
- `http://localhost:8000/health` (si estás probando localmente)
- O la URL de tu app en Railway + `/health`

Deberías ver:
```json
{
  "status": "healthy",
  "database": "connected",
  "whatsapp_api": "configured"
}
```

### 4. Verificar webhook en Meta (si no lo has hecho)

1. Ve a [Meta for Developers](https://developers.facebook.com/)
2. Selecciona tu app de WhatsApp
3. Ve a **Configuration** → **Webhook**
4. **Callback URL**: `https://tu-app.railway.app/webhook`
   - Si estás probando localmente, usa [ngrok](https://ngrok.com/) para exponer tu localhost
5. **Verify Token**: El mismo que pusiste en `WHATSAPP_VERIFY_TOKEN`
6. **Webhook fields**: Selecciona `messages`

### 5. Probar en WhatsApp

Envía un mensaje desde WhatsApp al número de tu bot con alguna de estas frases:

#### Mensajes de prueba para disponibilidad:

```
¿Tienen disponibilidad?
¿Hay horarios disponibles?
disponibilidad para mañana
¿Qué días tienen disponible?
quiero reservar
disponibilidad próxima semana
```

#### Respuestas esperadas:

El bot debería responder con algo como:

```
✅ ¡Tenemos disponibilidad!

📅 Domingo 02/11/2025: 12:00, 14:00, 16:00, 18:00, 19:00
📅 Lunes 03/11/2025: 10:00, 12:00, 14:00, 16:00, 18:00, 19:00
...

👥 ¿Para cuántas personas sería?
Puedo ayudarte a reservar el horario perfecto.

💡 También puedes reservar directamente aquí:
https://whatsapp.hotboat.cl/booking
```

## 🔍 Verificar logs

### Si el servidor está local:

En la terminal donde corriste `uvicorn`, deberías ver logs como:

```
INFO:     Processing message from Test User: ¿Tienen disponibilidad?
INFO:     Checking availability
INFO:     Found 43 available slots between 2025-11-02 and 2025-11-09
```

### Si el servidor está en Railway:

1. Ve a tu proyecto en Railway
2. Haz clic en tu servicio
3. Ve a la pestaña **Deployments** → selecciona el deployment activo
4. Revisa los logs en tiempo real

## 🐛 Solución de problemas

### El bot no responde

1. **Verifica que el webhook esté funcionando**:
   - Revisa los logs del servidor
   - Verifica que Meta esté enviando mensajes al webhook

2. **Verifica la conexión a la base de datos**:
   ```bash
   python test_availability.py
   ```
   (Asegúrate de tener las variables de entorno configuradas)

3. **Verifica que detecte consultas de disponibilidad**:
   - Revisa los logs: debería decir "Checking availability"
   - Si no, el mensaje podría estar siendo procesado por FAQ o AI

### El bot responde pero con error

1. **Revisa los logs del servidor** para ver el error específico
2. **Verifica la conexión a PostgreSQL**:
   - La URL de DATABASE_URL es correcta
   - El servidor de Railway tiene acceso a la base de datos

3. **Verifica que la tabla existe**:
   ```sql
   SELECT COUNT(*) FROM booknetic_appointments;
   ```

### No muestra disponibilidad

1. **Verifica que haya appointments en la base de datos**:
   ```sql
   SELECT * FROM booknetic_appointments 
   WHERE starts_at >= NOW() 
   LIMIT 10;
   ```

2. **Verifica los horarios de operación**:
   - Están configurados en `app/availability/availability_config.py`
   - Por defecto: [10, 12, 14, 16, 18, 19]

## 📊 Endpoints útiles para debugging

### Verificar salud del sistema:
```
GET /health
```

### Ver conversaciones recientes:
```
GET /conversations?limit=10
```

### Ver appointments próximos:
```
GET /appointments?days_ahead=7
```

## ✨ Palabras clave que activan disponibilidad

El sistema detecta consultas de disponibilidad si el mensaje contiene alguna de estas palabras:

- `disponibilidad`
- `disponible`
- `horario`
- `cuándo` / `cuando`
- `fecha`
- `día`
- `reservar`
- `reserva`
- `agendar`

## 🎯 Ejemplos de mensajes que funcionan

✅ **Estos activarán el sistema de disponibilidad:**
- "¿Tienen disponibilidad?"
- "Quiero saber los horarios disponibles"
- "¿Cuándo puedo reservar?"
- "¿Hay disponibilidad para mañana?"
- "Quiero agendar un tour"

❌ **Estos NO activarán disponibilidad (serán procesados por AI/FAQ):**
- "Hola"
- "¿Cuánto cuesta?"
- "¿Dónde están ubicados?"
- "Cuéntame sobre los tours"

## 🚀 Próximos pasos

Una vez que confirmes que funciona:

1. ✅ Prueba con diferentes tipos de consultas
2. ✅ Verifica que muestre horarios correctos
3. ✅ Prueba con "mañana", "próxima semana", etc.
4. ⏳ Monitorea los logs en producción
5. ⏳ Ajusta horarios si es necesario

## 📞 Si necesitas ayuda

- Revisa los logs del servidor
- Verifica que todas las variables de entorno estén configuradas
- Prueba con `test_availability.py` primero para verificar la base de datos

---

**¡Listo para probar!** 🎉 Envía un mensaje de WhatsApp y deberías recibir la disponibilidad en tiempo real.




