# 🔐 Guía: Token de Verificación del Webhook de WhatsApp

## 📋 Resumen Rápido

Tu **WHATSAPP_VERIFY_TOKEN** actual (local): `123456`

Este token es una **contraseña secreta que tú defines**, no la genera Meta/WhatsApp.

---

## 🔍 Encontrar tu Token Actual

### **En Railway (Production/Staging):**

1. Ve a: https://railway.app
2. Selecciona tu proyecto: `hotboat-whatsapp`
3. Selecciona el servicio (Production o Staging)
4. Pestaña: **Variables**
5. Busca: `WHATSAPP_VERIFY_TOKEN`

### **Localmente (.env):**
```bash
WHATSAPP_VERIFY_TOKEN=123456
```

---

## 🛠️ Cómo Configurar el Webhook en Meta

### Paso 1: Acceder a Meta Business Suite
1. Ve a: https://business.facebook.com/
2. Selecciona tu **App de WhatsApp Business**
3. En el menú lateral: **WhatsApp** > **Configuración**
4. Sección: **Webhooks**

### Paso 2: Configurar el Webhook

Haz clic en **"Editar"** o **"Configurar webhook"** e ingresa:

#### **Callback URL:**
```
# Para Production:
https://hotboat-whatsapp-production.up.railway.app/webhook

# Para Staging:
https://hotboat-whatsapp-staging.up.railway.app/webhook
```

#### **Verify Token:**
```
# El mismo token que configuraste en Railway para ese ambiente
# Por ejemplo: 123456
```

### Paso 3: Verificar y Guardar
1. Haz clic en **"Verificar y Guardar"**
2. Meta llamará a tu servidor con el token
3. Si coincide, ✅ el webhook quedará configurado
4. Si no coincide, ❌ verás un error

---

## ⚠️ Mejores Prácticas

### 🔒 Seguridad:

1. **Usa tokens diferentes para cada ambiente:**
   ```bash
   # Production
   WHATSAPP_VERIFY_TOKEN=HotBoat_Prod_Token_2026_Secret
   
   # Staging
   WHATSAPP_VERIFY_TOKEN=HotBoat_Staging_Token_2026_Secret
   ```

2. **Características de un buen token:**
   - ✅ Mínimo 12 caracteres
   - ✅ Combina letras y números
   - ✅ No uses palabras comunes
   - ✅ Incluye mayúsculas y minúsculas

### 🎯 Recomendación:

```bash
# Ejemplo de token seguro:
WHATSAPP_VERIFY_TOKEN=HbWh4t5App2026_Pr0d_S3cr3t_T0k3n
```

---

## 🧪 Probar el Webhook

### **Probar localmente:**

1. Inicia tu servidor local:
   ```bash
   uvicorn app.main:app --reload
   ```

2. Abre en tu navegador:
   ```
   http://localhost:8000/webhook?hub.mode=subscribe&hub.verify_token=123456&hub.challenge=test123
   ```

3. **Resultado esperado:** Debería devolver `test123`

### **Probar en Railway:**

```
https://tu-dominio.railway.app/webhook?hub.mode=subscribe&hub.verify_token=TU_TOKEN&hub.challenge=test123
```

---

## 🚨 Problemas Comunes

### ❌ Error: "Verification Failed"

**Causa:** El token no coincide

**Solución:**
1. Verifica que el token en Railway sea exactamente el mismo que ingresas en Meta
2. No debe tener espacios al inicio o final
3. Es case-sensitive (distingue mayúsculas de minúsculas)

### ❌ Error: "Cannot reach callback URL"

**Causa:** El servidor no está accesible

**Solución:**
1. Verifica que el deployment en Railway esté activo
2. Prueba acceder a: `https://tu-dominio.railway.app/health`
3. Revisa los logs en Railway

### ❌ Error: Webhook configurado pero no recibe mensajes

**Causa:** Falta suscribirse a los campos

**Solución:**
1. En Meta Business Suite > Webhooks
2. Haz clic en **"Administrar campos de webhook"**
3. Asegúrate de estar suscrito a:
   - ✅ `messages`
   - ✅ `message_echoes` (opcional)

---

## 📝 Dónde se Usa en el Código

El token se verifica en: `app/main.py`

```python
@app.get("/webhook")
async def webhook_verify(request: Request):
    """
    Verificación del webhook de WhatsApp
    """
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    
    # Verifica que el token coincida
    if verify_webhook(mode, token, settings.whatsapp_verify_token):
        return Response(content=challenge, media_type="text/plain")
    else:
        raise HTTPException(status_code=403, detail="Verification failed")
```

---

## 🔗 Referencias

- [Documentación oficial de Meta - Webhooks](https://developers.facebook.com/docs/whatsapp/cloud-api/guides/set-up-webhooks)
- [Verificación de webhooks](https://developers.facebook.com/docs/graph-api/webhooks/getting-started#verification-requests)

---

**Última actualización:** 23 de enero de 2026  
**Ambiente:** Production & Staging
