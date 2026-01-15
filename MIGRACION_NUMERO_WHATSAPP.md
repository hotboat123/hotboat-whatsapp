# 📱 Guía de Migración: Cambio de Número de WhatsApp

## 🎯 Situación Actual

- ✅ Bot ya está activo
- ✅ Número de teléfono del bot ha cambiado
- ✅ Necesitas mantener el historial de conversaciones anteriores

## 📋 Proceso Completo de Migración

### Paso 1: Exportar Conversaciones del Número Anterior

Tienes varias opciones dependiendo de cómo tengas las conversaciones:

#### Opción A: Si tienes acceso a WhatsApp Business Manager

1. Ve a **WhatsApp Business Manager** → **Message Templates** o **Conversations**
2. Si hay una opción de exportación, úsala
3. O manualmente, copia las conversaciones importantes

#### Opción B: Si tienes las conversaciones en WhatsApp Desktop/App

1. Abre cada conversación importante
2. Exporta el chat (tres puntos → "Exportar chat")
3. Esto te dará archivos `.txt` o `.zip`

#### Opción C: Si ya tienes los datos en otra base de datos/sistema

1. Exporta a CSV o JSON desde tu sistema actual
2. Adapta el formato según el template que crearemos

### Paso 2: Preparar el Formato de Importación

Ejecuta el script para crear un template:

```bash
python import_whatsapp_conversations.py template
```

Esto creará `conversations_import_template.json` con el formato correcto.

### Paso 3: Convertir tus Conversaciones al Formato Correcto

Necesitas crear un archivo JSON o CSV con este formato:

#### Formato JSON (`conversations.json`):

```json
[
  {
    "phone_number": "56912345678",
    "customer_name": "Nombre del Cliente",
    "conversations": [
      {
        "message": "Mensaje que envió el cliente",
        "response": "Respuesta que se le dio",
        "timestamp": "2025-01-15T10:00:00Z",
        "direction": "incoming",
        "message_id": "msg_123_optional"
      },
      {
        "message": "Siguiente mensaje del cliente",
        "response": "Siguiente respuesta",
        "timestamp": "2025-01-15T10:05:00Z",
        "direction": "incoming",
        "message_id": "msg_124_optional"
      }
    ]
  },
  {
    "phone_number": "56987654321",
    "customer_name": "Otro Cliente",
    "conversations": [...]
  }
]
```

#### Formato CSV (`conversations.csv`):

```csv
phone_number,customer_name,message,response,timestamp,direction,message_id
56912345678,Juan Pérez,Hola,¡Hola Juan!,2025-01-15 10:00:00,incoming,msg_123
56912345678,Juan Pérez,¿Cuánto cuesta?,Los precios...,2025-01-15 10:05:00,incoming,msg_124
```

**Notas importantes:**
- `phone_number`: Formato sin espacios ni `+`, ejemplo: `56912345678`
- `timestamp`: Formato ISO o `YYYY-MM-DD HH:MM:SS`
- `direction`: `"incoming"` para mensajes del cliente, `"outgoing"` para tus respuestas
- `message_id`: Opcional, pero ayuda a evitar duplicados

### Paso 4: Actualizar Configuración del Nuevo Número

#### En Railway / Variables de Entorno:

Actualiza estas variables con las credenciales del **NUEVO número**:

```env
WHATSAPP_API_TOKEN=token_del_nuevo_numero
WHATSAPP_PHONE_NUMBER_ID=phone_id_del_nuevo_numero
WHATSAPP_BUSINESS_ACCOUNT_ID=account_id_del_nuevo_numero
WHATSAPP_VERIFY_TOKEN=tu_verify_token
```

#### En Meta for Developers:

1. Ve a tu app de WhatsApp
2. Actualiza el webhook con la URL correcta
3. Verifica que el `WHATSAPP_VERIFY_TOKEN` coincida
4. Confirma que el nuevo número está configurado correctamente

### Paso 5: Verificar que la Base de Datos Está Lista

Ejecuta las migraciones (si no las ejecutaste antes):

```bash
python run_migrations.py
```

Esto crea las tablas necesarias si no existen.

### Paso 6: Importar las Conversaciones

Una vez que tienes el archivo preparado:

```bash
# Para JSON
python import_whatsapp_conversations.py conversations.json

# Para CSV
python import_whatsapp_conversations.py conversations.csv csv
```

Verás algo como:
```
✅ Imported 15 conversations for 56912345678 (Juan Pérez)
✅ Imported 8 conversations for 56987654321 (María González)
...
✅ Total: 47 conversations imported
```

### Paso 7: Verificar que la Importación Funcionó

Puedes verificar usando la API:

```bash
# Ver todos los leads importados
curl http://localhost:8000/leads

# Ver historial de un contacto específico
curl http://localhost:8000/leads/56912345678
```

### Paso 8: Probar que el Bot Funciona con el Nuevo Número

1. **Envía un mensaje de prueba** desde WhatsApp al nuevo número
2. **El bot debería responder** automáticamente
3. **Si el contacto tiene historial importado**, el bot lo recordará y usará ese contexto

### Paso 9: Clasificar Leads Importados (Opcional pero Recomendado)

Una vez importadas las conversaciones, puedes clasificar los leads:

```bash
# Clasificar como potencial cliente
curl -X PUT http://localhost:8000/leads/56912345678/status \
  -H "Content-Type: application/json" \
  -d '{
    "lead_status": "potential_client",
    "notes": "Cliente interesado, ya preguntó por precios"
  }'

# Clasificar como mal lead
curl -X PUT http://localhost:8000/leads/56987654321/status \
  -H "Content-Type: application/json" \
  -d '{
    "lead_status": "bad_lead",
    "notes": "Solo spam o no mostró interés real"
  }'
```

## ✅ Checklist de Migración

- [ ] Exportar conversaciones del número anterior
- [ ] Convertir al formato JSON o CSV
- [ ] Actualizar variables de entorno con nuevo número
- [ ] Verificar webhook en Meta for Developers
- [ ] Ejecutar migraciones de base de datos
- [ ] Importar conversaciones al nuevo sistema
- [ ] Verificar que la importación funcionó
- [ ] Probar que el bot responde con el nuevo número
- [ ] Clasificar leads importantes (opcional)

## 🔍 Verificación Post-Migración

Después de la migración, verifica:

1. **El bot responde correctamente** con el nuevo número
2. **Las conversaciones anteriores están disponibles** cuando alguien escribe
3. **El contexto se mantiene** - el bot recuerda conversaciones pasadas
4. **Los leads están clasificados** (al menos los importantes)

## 💡 Tips Importantes

### Sobre los Números de Teléfono

- El historial está ligado al **número de teléfono del cliente**, no al número del bot
- Si un cliente escribe al nuevo número, el bot cargará automáticamente su historial importado
- No necesitas hacer nada especial - el sistema funciona automáticamente

### Sobre el Formato de Números

Asegúrate de que los números estén en formato consistente:
- ✅ Correcto: `56912345678` (Chile, sin `+` ni espacios)
- ❌ Incorrecto: `+56 9 1234 5678` o `56-9-1234-5678`

### Sobre las Fechas

- El formato de timestamp es flexible
- Acepta: `2025-01-15T10:00:00Z` o `2025-01-15 10:00:00`
- Si no tienes fechas exactas, puedes usar fechas aproximadas o dejar `null`

## 🆘 Si Algo Sale Mal

### Problema: "No se pueden importar las conversaciones"

1. Verifica el formato del archivo JSON/CSV
2. Revisa que los números de teléfono estén en formato correcto
3. Asegúrate de que la base de datos esté conectada

### Problema: "El bot no responde con el nuevo número"

1. Verifica las variables de entorno (especialmente `WHATSAPP_PHONE_NUMBER_ID`)
2. Confirma que el webhook está configurado correctamente en Meta
3. Revisa los logs del servidor para ver errores

### Problema: "No se carga el historial importado"

1. Verifica que las conversaciones se importaron correctamente (`GET /leads`)
2. Asegúrate de que el número de teléfono coincide exactamente
3. Revisa los logs cuando alguien escribe - debería mostrar "Loaded X messages from history"

## 📞 Soporte

Si tienes problemas durante la migración:
1. Revisa los logs del servidor
2. Verifica que todas las variables de entorno estén correctas
3. Prueba importar solo un contacto primero para verificar el formato




