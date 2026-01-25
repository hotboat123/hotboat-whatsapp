# 📁 Lista de Archivos - Sistema de Notificaciones No Leídos

## 🆕 Archivos Nuevos Creados

### Migración y Scripts
1. **`migrations/008_add_unread_count.sql`**
   - Migración SQL para agregar campos unread_count y last_read_at
   - Crea índices para optimizar queries

2. **`run_migration_008.py`**
   - Script Python para ejecutar la migración
   - Incluye verificación de columnas

3. **`test_unread_notifications.py`**
   - Script de prueba del sistema completo
   - Simula flujo de mensajes y verificaciones

### Documentación
4. **`NOTIFICACIONES_NO_LEIDOS.md`**
   - Guía completa del sistema
   - Arquitectura, flujo, troubleshooting

5. **`RESUMEN_NOTIFICACIONES.md`**
   - Resumen ejecutivo de la implementación
   - Vista previa y próximos pasos

6. **`DEPLOYMENT_NOTIFICACIONES.md`**
   - Guía paso a paso para deployment
   - Checklist, troubleshooting, rollback

7. **`ARCHIVOS_MODIFICADOS.md`** (este archivo)
   - Lista completa de cambios

## ✏️ Archivos Modificados

### Backend - Base de Datos

8. **`app/db/leads.py`**
   - **Líneas 32-38**: Actualizado query para incluir unread_count y last_read_at
   - **Líneas 61-72**: Actualizado return de get_or_create_lead con nuevos campos
   - **Líneas 85-96**: Actualizado return de nuevo lead con valores default
   - **Líneas 189-207**: Actualizado get_leads_by_status con nuevos campos
   - **Líneas 211-224**: Actualizado return de leads con nuevos campos
   - **Líneas 435-502**: Agregadas nuevas funciones:
     - `increment_unread_count(phone_number)` 
     - `mark_conversation_as_read(phone_number)`

9. **`app/db/queries.py`**
   - **Líneas 322-343**: Actualizado get_recent_conversations con JOIN a whatsapp_leads
   - **Línea 347**: Agregado campo unread_count en row parsing
   - **Líneas 369-375**: Agregado unread_count en return dict

### Backend - Webhook y API

10. **`app/whatsapp/webhook.py`**
    - **Línea 9**: Importado increment_unread_count
    - **Líneas 120-135**: Agregado increment después de save (texto, bot disabled)
    - **Líneas 227-241**: Agregado increment después de save (texto, bot enabled)
    - **Líneas 312-327**: Agregado increment después de save (imagen, bot disabled)
    - **Líneas 409-425**: Agregado increment después de save (imagen, bot enabled)
    - **Líneas 492-507**: Agregado increment después de save (audio, bot disabled)
    - **Líneas 586-602**: Agregado increment después de save (audio, bot enabled)

11. **`app/main.py`**
    - **Líneas 15-21**: Agregado mark_conversation_as_read en imports
    - **Líneas 292-305**: Nuevo endpoint PUT /api/conversations/{phone_number}/mark-read

### Frontend

12. **`app/static/styles.css`**
    - **Líneas 179-187**: Actualizado .conversation-header con align-items
    - **Líneas 189-194**: Actualizado .conversation-name con flex display
    - **Líneas 196-205**: Nuevo .unread-indicator para badge verde

13. **`app/static/app.js`**
    - **Líneas 301-323**: Actualizado renderConversations() con lógica de badge
    - **Líneas 326-352**: Actualizado selectConversation() con llamada a markAsRead
    - **Líneas 1384-1411**: Nueva función markConversationAsRead()

## 📊 Estadísticas de Cambios

```
Total de archivos: 13
  - Nuevos: 7
  - Modificados: 6

Líneas de código:
  - Backend (Python): ~200 líneas nuevas
  - Frontend (JS/CSS): ~50 líneas nuevas
  - SQL: ~15 líneas nuevas
  - Documentación: ~600 líneas

Funciones nuevas:
  - increment_unread_count()
  - mark_conversation_as_read()
  - markConversationAsRead()
  - run_migration() (en script)
  - test_unread_system() (en test)

Endpoints nuevos:
  - PUT /api/conversations/{phone_number}/mark-read
```

## 🔍 Resumen de Cambios por Tipo

### 1. Base de Datos
- ✅ 2 nuevas columnas en whatsapp_leads
- ✅ 1 nuevo índice
- ✅ 1 nueva migración SQL

### 2. Backend Logic
- ✅ 2 nuevas funciones en leads.py
- ✅ 1 nuevo endpoint en main.py
- ✅ 6 puntos de integración en webhook.py
- ✅ 1 query actualizada en queries.py

### 3. Frontend
- ✅ 1 nuevo estilo CSS para badge
- ✅ 1 función actualizada (renderConversations)
- ✅ 1 función actualizada (selectConversation)
- ✅ 1 nueva función (markConversationAsRead)

### 4. Testing y Scripts
- ✅ 1 script de migración
- ✅ 1 script de testing

### 5. Documentación
- ✅ 3 guías completas (funcionalidad, deployment, resumen)

## 🎯 Archivos Críticos para Review

Si quieres hacer code review, estos son los más importantes:

1. **`app/db/leads.py`** - Lógica principal del contador
2. **`app/whatsapp/webhook.py`** - Integración con flujo de mensajes
3. **`app/static/app.js`** - UI y UX del indicador
4. **`migrations/008_add_unread_count.sql`** - Cambios en BD

## 📝 Notas

- Todos los cambios son backwards compatible
- No se eliminó código existente
- No se modificaron tablas existentes (solo se agregaron campos)
- Los tests existentes deberían seguir funcionando

## 🔗 Referencias Cruzadas

- **Migración DB** → `migrations/008_add_unread_count.sql`
- **Funciones Backend** → `app/db/leads.py` líneas 435-502
- **API Endpoint** → `app/main.py` líneas 292-305
- **UI Components** → `app/static/app.js` líneas 301-323
- **Estilos** → `app/static/styles.css` líneas 196-205

---

**Generado**: Enero 2026
**Implementación**: Sistema de Notificaciones de Mensajes No Leídos v1.0
