# 🔔 Sistema de Notificaciones de Mensajes No Leídos

## 📋 Descripción

Sistema de notificaciones similar a WhatsApp que muestra un indicador visual en el chat cuando hay mensajes no leídos. El indicador desaparece automáticamente al abrir la conversación.

## ✨ Características

- **Indicador visual**: Badge verde con el número de mensajes no leídos
- **Actualización automática**: Se incrementa cuando llegan mensajes nuevos
- **Marca como leído**: Se resetea al abrir el chat
- **Persistencia**: Los contadores se guardan en la base de datos
- **Sincronización**: Funciona en tiempo real con el sistema de conversaciones

## 🗄️ Cambios en Base de Datos

### Nueva Migración: `008_add_unread_count.sql`

Agrega dos nuevos campos a la tabla `whatsapp_leads`:

```sql
- unread_count: INTEGER DEFAULT 0
  Contador de mensajes no leídos del contacto

- last_read_at: TIMESTAMP DEFAULT NULL
  Última vez que el admin leyó la conversación
```

### Ejecutar Migración

```bash
# Opción 1: Script dedicado
python run_migration_008.py

# Opción 2: Script general
python run_migrations.py
```

## 🔧 Componentes Implementados

### Backend

1. **`app/db/leads.py`**
   - `increment_unread_count()`: Incrementa contador al recibir mensaje
   - `mark_conversation_as_read()`: Resetea contador al abrir chat
   - Actualizado `get_or_create_lead()` para incluir campos nuevos
   - Actualizado `get_leads_by_status()` para incluir campos nuevos

2. **`app/db/queries.py`**
   - Actualizado `get_recent_conversations()` con JOIN a `whatsapp_leads`
   - Incluye `unread_count` en respuesta de API

3. **`app/whatsapp/webhook.py`**
   - Llama a `increment_unread_count()` después de guardar cada mensaje entrante
   - Aplica a mensajes de texto, imágenes y audios

4. **`app/main.py`**
   - Nuevo endpoint: `PUT /api/conversations/{phone_number}/mark-read`
   - Marca conversación como leída desde el frontend

### Frontend

1. **`app/static/styles.css`**
   - `.unread-indicator`: Badge verde circular
   - Styling responsivo y consistente con WhatsApp

2. **`app/static/app.js`**
   - Actualizado `renderConversations()` para mostrar badge
   - Actualizado `selectConversation()` para marcar como leído
   - Nueva función `markConversationAsRead()`
   - Actualización local del estado para UX inmediata

## 🎯 Flujo de Funcionamiento

### Cuando llega un mensaje:

1. Webhook recibe mensaje de WhatsApp
2. Guarda conversación en DB (`save_conversation`)
3. Incrementa contador (`increment_unread_count`)
4. Frontend actualiza lista en próximo refresh (cada 10s)
5. Badge verde aparece con el número de mensajes

### Cuando el admin abre el chat:

1. Usuario hace click en conversación
2. `selectConversation()` carga mensajes
3. Llama a `markConversationAsRead()` en background
4. Backend resetea `unread_count` a 0
5. Frontend actualiza estado local
6. Badge desaparece inmediatamente

## 📊 Estructura de Datos

### Respuesta API `/api/conversations`:

```json
{
  "conversations": [
    {
      "phone_number": "56912345678",
      "customer_name": "Juan Pérez",
      "last_message": "Hola, consulta sobre precios",
      "last_message_at": "2026-01-23T15:30:00-03:00",
      "unread_count": 3,  // ← NUEVO
      "direction": "incoming"
    }
  ]
}
```

### Respuesta API `/leads/{phone_number}`:

```json
{
  "lead": {
    "id": 123,
    "phone_number": "56912345678",
    "customer_name": "Juan Pérez",
    "unread_count": 3,           // ← NUEVO
    "last_read_at": "2026-01-23T14:00:00-03:00",  // ← NUEVO
    "bot_enabled": true,
    ...
  }
}
```

## 🎨 Interfaz de Usuario

### Aspecto Visual

```
┌─────────────────────────────────┐
│ 💬 Conversations          🔄    │
├─────────────────────────────────┤
│ Juan Pérez            (3) 15:30 │ ← Badge verde con número
│ Consulta sobre precios...       │
├─────────────────────────────────┤
│ María González           14:20  │ ← Sin badge (leído)
│ Gracias por la info             │
└─────────────────────────────────┘
```

### Estados del Badge

- **Con mensajes**: Badge verde circular con número
- **Sin mensajes**: Sin badge
- **Al abrir**: Badge desaparece inmediatamente

## 🧪 Pruebas

### Prueba Manual

1. **Recibir mensaje nuevo**:
   - Envía un mensaje desde WhatsApp
   - Verifica que aparezca badge en Kia-Ai
   - Número debe coincidir con mensajes no leídos

2. **Abrir conversación**:
   - Click en chat con badge
   - Badge debe desaparecer inmediatamente
   - Si sales y vuelves a entrar, no debe aparecer

3. **Múltiples mensajes**:
   - Envía varios mensajes sin leer
   - Badge debe mostrar el número correcto
   - Al abrir, todos se marcan como leídos

## 🔍 Troubleshooting

### Badge no aparece

```bash
# Verificar que la migración se ejecutó
psql $DATABASE_URL -c "SELECT column_name FROM information_schema.columns WHERE table_name = 'whatsapp_leads' AND column_name = 'unread_count';"

# Verificar datos
psql $DATABASE_URL -c "SELECT phone_number, unread_count FROM whatsapp_leads WHERE unread_count > 0;"
```

### Badge no desaparece al abrir

1. Verifica en la consola del navegador si hay errores
2. Verifica que el endpoint `/api/conversations/{phone}/mark-read` responda 200
3. Revisa logs del servidor

### Contador incorrecto

```sql
-- Resetear todos los contadores
UPDATE whatsapp_leads SET unread_count = 0;

-- Ver contadores actuales
SELECT phone_number, customer_name, unread_count 
FROM whatsapp_leads 
WHERE unread_count > 0
ORDER BY unread_count DESC;
```

## 📝 Notas Técnicas

- El contador solo se incrementa para mensajes **entrantes** (del cliente)
- Mensajes **salientes** (del bot o admin) no incrementan el contador
- La actualización es asíncrona para no bloquear el flujo principal
- El badge se actualiza localmente para mejor UX (no espera al servidor)

## 🚀 Mejoras Futuras

- [ ] Notificación de escritorio cuando llega mensaje
- [ ] Sonido de notificación
- [ ] Contador total de no leídos en el header
- [ ] Filtro para mostrar solo conversaciones no leídas
- [ ] Historial de última lectura por conversación

## 📚 Referencias

- Migración SQL: `migrations/008_add_unread_count.sql`
- Script de migración: `run_migration_008.py`
- Documentación de API: Ver endpoints en `app/main.py`
