# 🔧 Solución a los Problemas de Kia-Ai

## ✅ Problemas Identificados y Solucionados

### 1. ❌ Error 401 - No puedes enviar mensajes

**Causa:**  
Tu archivo `.env` tiene `WHATSAPP_PHONE_NUMBER_ID=your_phone_number_id_here` (valor de ejemplo).

**Solución:**  
Lee y sigue las instrucciones en: **[FIX_WHATSAPP_CREDENTIALS.md](FIX_WHATSAPP_CREDENTIALS.md)**

**Resumen rápido:**
1. Ve a: https://developers.facebook.com/apps
2. Selecciona tu app > WhatsApp > API Setup
3. Copia el **Phone Number ID** (número de 15 dígitos)
4. Copia el **Access Token** (texto largo de ~200 caracteres)
5. Actualiza tu `.env`:

```env
WHATSAPP_PHONE_NUMBER_ID=123456789012345
WHATSAPP_API_TOKEN=EAABsbCS1iHgBO7ZCZBfZCRO2c9ZAb3TqD8...
```

6. Reinicia el servidor:
```bash
python -m app.main
```

---

### 2. ❌ Los mensajes no se muestran correctamente

**Causa:**  
La estructura de datos en la base de datos tenía un formato diferente al que esperaba Kia-Ai.

**Solución:**  
✅ **Ya arreglado!** Actualicé las siguientes funciones:
- `get_conversation_history()` en `app/db/leads.py`
- `get_recent_conversations()` en `app/db/queries.py`

**Lo que cambió:**
- Ahora los mensajes se retornan con el campo `message_text` correcto
- Se manejan correctamente los mensajes `incoming` y `outgoing`
- Se agrupa correctamente por número de teléfono en la lista de conversaciones

---

## 🔄 Qué Hacer Ahora

### Paso 1: Detén el Servidor

En la terminal donde corre el servidor, presiona:
```
Ctrl + C
```

### Paso 2: Actualiza las Credenciales

1. Abre tu `.env`:
```bash
notepad .env
```

2. Busca estas líneas y reemplázalas con tus valores reales:
```env
WHATSAPP_API_TOKEN=tu_token_real_aqui
WHATSAPP_PHONE_NUMBER_ID=tu_phone_id_real_aqui
```

3. Guarda el archivo

### Paso 3: Reinicia el Servidor

```bash
python -m app.main
```

### Paso 4: Prueba Kia-Ai

1. Abre: http://localhost:8000
2. Deberías ver:
   - ✅ Conversaciones en el sidebar izquierdo
   - ✅ Mensajes completos cuando haces click
   - ✅ Poder enviar mensajes sin error 401

---

## 📊 Estado de tu Base de Datos

Según la verificación:
- ✅ **616 conversaciones** en total
- ✅ Conversaciones del número: **56977577307** (Tomo)
- ✅ Los mensajes SÍ tienen contenido

---

## 🧪 Verificar que Todo Funciona

### Test 1: Ver Conversaciones

```bash
# Abre en tu navegador:
http://localhost:8000

# Deberías ver conversaciones en el sidebar
```

### Test 2: Ver Mensajes de una Conversación

```bash
# En Kia-Ai, click en cualquier conversación
# Deberías ver los mensajes completos, no solo "mié"
```

### Test 3: Enviar un Mensaje

```bash
# En Kia-Ai:
# 1. Click en una conversación
# 2. Escribe un mensaje
# 3. Click "Send"
# 
# NO deberías ver error 401
# El mensaje debería enviarse correctamente
```

---

## ❗ Si Aún No Se Ven los Mensajes

Si después de reiniciar aún no se ven los mensajes completos:

### Diagnóstico Manual

```bash
# Verifica la API directamente en tu navegador:
http://localhost:8000/api/conversations/56977577307

# Deberías ver un JSON con tus mensajes
```

### Verifica la Consola del Navegador

1. Abre Kia-Ai: http://localhost:8000
2. Presiona F12 (abrir DevTools)
3. Ve a la pestaña "Console"
4. Click en una conversación
5. Mira si hay errores en la consola

---

## 📝 Resumen de Cambios Realizados

### Archivos Modificados:

1. **`app/config.py`**
   - ✅ Agregados campos de email SMTP

2. **`app/db/leads.py`**
   - ✅ Actualizada función `get_conversation_history()`
   - ✅ Ahora retorna mensajes en formato correcto para Kia-Ai

3. **`app/db/queries.py`**
   - ✅ Actualizada función `get_recent_conversations()`
   - ✅ Ahora agrupa por teléfono y muestra último mensaje

### Documentos Creados:

1. **`FIX_WHATSAPP_CREDENTIALS.md`**
   - Guía completa para configurar credenciales de WhatsApp

2. **`SOLUCION_MENSAJES.md`** (este archivo)
   - Resumen de problemas y soluciones

3. **`check_database_content.py`**
   - Script para verificar contenido de la base de datos

---

## 🎯 Checklist Final

Antes de usar Kia-Ai, verifica que:

- [ ] Actualizaste el archivo `.env` con tus credenciales reales
- [ ] `WHATSAPP_PHONE_NUMBER_ID` NO es `your_phone_number_id_here`
- [ ] `WHATSAPP_API_TOKEN` NO es `your_token_here`
- [ ] Reiniciaste el servidor después de actualizar `.env`
- [ ] Puedes abrir http://localhost:8000
- [ ] Ves conversaciones en el sidebar
- [ ] Al hacer click, ves los mensajes completos
- [ ] Puedes enviar mensajes sin error 401

---

## 🆘 Soporte Adicional

### Si el Error 401 Persiste:

1. Verifica tus credenciales en Meta Developers
2. Lee **[FIX_WHATSAPP_CREDENTIALS.md](FIX_WHATSAPP_CREDENTIALS.md)**
3. Asegúrate de que el token no haya expirado

### Si los Mensajes No Se Muestran:

1. Abre la consola del navegador (F12)
2. Ve a la pestaña "Network"
3. Filtra por "conversations"
4. Mira la respuesta de la API
5. Verifica que retorne datos en formato JSON

### Contacto:

Si nada funciona, proporcióname:
1. El error exacto de la consola
2. La respuesta de: http://localhost:8000/api/conversations
3. Screenshot de Kia-Ai

---

## ✅ ¡Listo!

Después de seguir estos pasos, Kia-Ai debería funcionar perfectamente:
- ✅ Ver todas las conversaciones
- ✅ Ver mensajes completos
- ✅ Enviar mensajes personalizados
- ✅ Sin errores 401

**¡Disfruta de Kia-Ai! 💬**

