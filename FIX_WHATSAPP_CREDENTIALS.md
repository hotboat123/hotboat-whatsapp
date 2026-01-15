# 🔧 Cómo Arreglar el Error 401 de WhatsApp

## El Problema

Estás viendo este error:
```
Error sending message: Client error '401 Unauthorized' 
for url 'https://graph.facebook.com/v18.0/your_phone_number_id_here/messages'
```

**Causa:** Tu archivo `.env` tiene `WHATSAPP_PHONE_NUMBER_ID=your_phone_number_id_here` que es un valor de ejemplo, no tu ID real.

---

## ✅ Solución: Configura tus Credenciales de WhatsApp

### Paso 1: Abre tu archivo `.env`

```bash
notepad .env
```

### Paso 2: Encuentra tu WhatsApp Phone Number ID

#### Opción A: Meta Business Manager

1. Ve a: https://business.facebook.com/
2. Selecciona tu cuenta de negocio
3. Click en **"WhatsApp Manager"** (o "WhatsApp Business Platform")
4. Selecciona tu número de teléfono
5. Busca el **"Phone Number ID"** (es un número largo)

#### Opción B: Meta Developers

1. Ve a: https://developers.facebook.com/apps
2. Selecciona tu aplicación
3. En el menú lateral, click en **"WhatsApp" > "API Setup"**
4. Verás **"Phone Number ID"** - Cópialo

#### Opción C: Desde el Panel de Configuración

1. Ve a: https://developers.facebook.com/apps/YOUR_APP_ID/whatsapp-business/wa-settings/
2. En la sección "Phone numbers", verás el ID de cada número

**Ejemplo de Phone Number ID:**
```
123456789012345
```
(Es un número de 15 dígitos)

### Paso 3: Encuentra tu Access Token

En el mismo lugar donde encontraste el Phone Number ID:

1. Busca **"Temporary access token"** o **"Access Token"**
2. Click en **"Generate"** o **"Copy"**
3. Copia el token completo

**Ejemplo de Access Token:**
```
EAABsbCS1iHgBO7ZCZBfZCRO2c9ZAb3TqD8...
```
(Es un texto largo de ~200 caracteres)

### Paso 4: Actualiza tu archivo `.env`

Reemplaza estos valores en tu `.env`:

```env
# ❌ INCORRECTO (valores de ejemplo)
WHATSAPP_PHONE_NUMBER_ID=your_phone_number_id_here
WHATSAPP_API_TOKEN=your_token_here

# ✅ CORRECTO (tus valores reales)
WHATSAPP_PHONE_NUMBER_ID=123456789012345
WHATSAPP_API_TOKEN=EAABsbCS1iHgBO7ZCZBfZCRO2c9ZAb3TqD8...
```

**Valores completos necesarios:**

```env
# WhatsApp Business API
WHATSAPP_API_TOKEN=tu_token_real_aqui
WHATSAPP_PHONE_NUMBER_ID=tu_phone_id_aqui
WHATSAPP_BUSINESS_ACCOUNT_ID=tu_business_account_id_aqui
WHATSAPP_VERIFY_TOKEN=cualquier_texto_secreto

# Ejemplo con valores FICTICIOS (reemplaza con los tuyos):
# WHATSAPP_API_TOKEN=EAABsbCS1iHgBO7ZCZBfZCRO2c9ZAb3TqD8ZAZCW9ZCqR5fhGHI...
# WHATSAPP_PHONE_NUMBER_ID=123456789012345
# WHATSAPP_BUSINESS_ACCOUNT_ID=987654321098765
# WHATSAPP_VERIFY_TOKEN=mi_token_secreto_12345
```

### Paso 5: Reinicia el Servidor

Después de actualizar el `.env`, reinicia Kia-Ai:

1. Detén el servidor (Ctrl+C en la terminal)
2. Inicia de nuevo:

```bash
python -m app.main
```

---

## 🧪 Verificar que Funciona

### Test 1: Verificar Configuración

```bash
python -c "from app.config import get_settings; s = get_settings(); print('Phone ID:', s.whatsapp_phone_number_id); print('Token:', s.whatsapp_api_token[:20] + '...')"
```

Deberías ver tus valores reales, no `your_phone_number_id_here`.

### Test 2: Enviar Mensaje de Prueba

1. Abre Kia-Ai: http://localhost:8000
2. Click en "New Message"
3. Ingresa un número de prueba (tu propio número)
4. Envía un mensaje
5. Verifica que llegue

---

## 🔍 Dónde Encontrar Cada Credencial

| Credencial | Dónde Encontrarla |
|------------|-------------------|
| **WHATSAPP_PHONE_NUMBER_ID** | Meta Developers > WhatsApp > API Setup > "Phone Number ID" |
| **WHATSAPP_API_TOKEN** | Meta Developers > WhatsApp > API Setup > "Temporary access token" |
| **WHATSAPP_BUSINESS_ACCOUNT_ID** | Meta Developers > WhatsApp > "WhatsApp Business Account ID" |
| **WHATSAPP_VERIFY_TOKEN** | Lo creas tú (cualquier texto secreto, ej: "mi_token_123") |

---

## ⚠️ Problemas Comunes

### Problema 1: Token Temporal Expiró

**Síntoma:** Funcionaba antes pero ahora da error 401

**Solución:** Los tokens temporales expiran. Necesitas:
1. Generar un **token permanente**
2. O regenerar el token temporal cada 24 horas

**Para token permanente:**
1. Ve a Meta Developers > WhatsApp > API Setup
2. Busca "Permanent access token" o "System User"
3. Crea un System User con permisos de WhatsApp
4. Genera un token permanente

### Problema 2: Phone Number ID Incorrecto

**Síntoma:** Error 401 incluso con token válido

**Solución:**
- Verifica que usas el **Phone Number ID**, no tu número de teléfono
- El Phone Number ID es diferente a tu número de WhatsApp
- Ejemplo: Phone Number ID: `123456789012345` ≠ Tu número: `+56977577307`

### Problema 3: Permisos Insuficientes

**Síntoma:** Error 403 o "insufficient permissions"

**Solución:**
1. Ve a Meta Developers > tu app
2. Click en **"WhatsApp" > "API Setup"**
3. Verifica que tu número esté **"Connected"** o **"Active"**
4. Asegúrate de tener permisos de **"whatsapp_business_messaging"**

---

## 📝 Ejemplo Completo de .env

```env
# Database
DATABASE_URL=postgresql://user:password@host:5432/database

# WhatsApp Business API (IMPORTANTE: Reemplaza con TUS valores)
WHATSAPP_API_TOKEN=EAABsbCS1iHgBO7ZCZBfZCRO2c9ZAb3TqD8ZAZCW9ZCqR5fhGHI
WHATSAPP_PHONE_NUMBER_ID=123456789012345
WHATSAPP_BUSINESS_ACCOUNT_ID=987654321098765
WHATSAPP_VERIFY_TOKEN=mi_token_secreto_123

# AI
GROQ_API_KEY=tu_groq_key

# Bot Info
BOT_NAME=Capitan HotBoat
BUSINESS_NAME=Hot Boat
BUSINESS_PHONE=+56 9 75780920
BUSINESS_EMAIL=info@hotboatchile.com
BUSINESS_WEBSITE=https://hotboatchile.com/es/

# Server
PORT=8000
HOST=0.0.0.0
ENVIRONMENT=production
```

---

## ✅ Checklist de Verificación

Antes de continuar, asegúrate de que:

- [ ] `WHATSAPP_PHONE_NUMBER_ID` NO es `your_phone_number_id_here`
- [ ] `WHATSAPP_API_TOKEN` NO es `your_token_here`
- [ ] El token tiene al menos 100 caracteres
- [ ] El Phone Number ID tiene ~15 dígitos
- [ ] Guardaste el archivo `.env`
- [ ] Reiniciaste el servidor

---

## 🆘 Si Aún No Funciona

1. **Verifica los logs:**
   ```bash
   # Mira los errores en la terminal donde corre el servidor
   ```

2. **Prueba manualmente la API:**
   ```bash
   curl -X POST https://graph.facebook.com/v18.0/TU_PHONE_ID/messages \
     -H "Authorization: Bearer TU_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "messaging_product": "whatsapp",
       "to": "56977577307",
       "type": "text",
       "text": { "body": "Test desde curl" }
     }'
   ```

3. **Verifica en Meta Developers:**
   - Ve a tu app
   - Click en "WhatsApp" > "API Setup"
   - Prueba enviar un mensaje desde ahí
   - Si funciona ahí pero no en Kia-Ai, el problema es de configuración

---

## 🎉 Todo Listo

Una vez configurado correctamente:

✅ Podrás enviar mensajes desde Kia-Ai
✅ Los mensajes llegarán a tus clientes
✅ No verás más errores 401

**Reinicia el servidor y prueba Kia-Ai nuevamente!**

```bash
python -m app.main
```

Luego abre: http://localhost:8000

