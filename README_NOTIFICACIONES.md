# 🔔 Sistema de Notificaciones de Mensajes No Leídos

> Sistema implementado similar a WhatsApp que muestra un indicador visual de mensajes no leídos en la interfaz Kia-Ai

## ⚡ Quick Start

```bash
# 1. Ejecutar migración
python run_migration_008.py

# 2. Reiniciar servidor
# (Railway, Heroku, o tu método preferido)

# 3. Probar
python test_unread_notifications.py
```

## ✨ Características

- **Badge visual verde** con número de mensajes no leídos
- **Auto-incremento** al recibir mensajes de WhatsApp
- **Auto-reset** al abrir la conversación
- **Persistencia** en base de datos
- **Tiempo real** sincronizado con el sistema

## 📚 Documentación Completa

- 📖 **Guía del Sistema**: [`NOTIFICACIONES_NO_LEIDOS.md`](NOTIFICACIONES_NO_LEIDOS.md)
- 🚀 **Deployment**: [`DEPLOYMENT_NOTIFICACIONES.md`](DEPLOYMENT_NOTIFICACIONES.md)
- 📝 **Resumen**: [`RESUMEN_NOTIFICACIONES.md`](RESUMEN_NOTIFICACIONES.md)
- 📁 **Archivos Modificados**: [`ARCHIVOS_MODIFICADOS.md`](ARCHIVOS_MODIFICADOS.md)

## 🎯 Cómo Funciona

```
1. Llega mensaje → Incrementa contador
2. Usuario abre chat → Resetea contador
3. Badge verde muestra número → Desaparece al abrir
```

## 🔧 Componentes

| Componente | Archivos |
|------------|----------|
| **Base de Datos** | `migrations/008_add_unread_count.sql` |
| **Backend** | `app/db/leads.py`, `app/whatsapp/webhook.py` |
| **API** | `app/main.py` (nuevo endpoint) |
| **Frontend** | `app/static/app.js`, `app/static/styles.css` |

## 📊 Estado de Implementación

- ✅ Base de datos - 2 nuevas columnas
- ✅ Backend - Funciones de incremento y reset
- ✅ Webhook - Integración con flujo de mensajes
- ✅ API - Endpoint para marcar como leído
- ✅ Frontend - Badge visual y lógica
- ✅ Testing - Script de verificación
- ✅ Documentación - Guías completas

## 🧪 Testing

```bash
# Test básico
python test_unread_notifications.py

# Test manual
# 1. Envía mensaje desde WhatsApp
# 2. Verifica badge en Kia-Ai
# 3. Abre conversación
# 4. Verifica que badge desaparezca
```

## 🆘 Troubleshooting Rápido

```bash
# Verificar migración
psql $DATABASE_URL -c "SELECT column_name FROM information_schema.columns WHERE table_name = 'whatsapp_leads' AND column_name = 'unread_count';"

# Ver contadores actuales
psql $DATABASE_URL -c "SELECT phone_number, customer_name, unread_count FROM whatsapp_leads WHERE unread_count > 0;"

# Resetear contadores
psql $DATABASE_URL -c "UPDATE whatsapp_leads SET unread_count = 0;"
```

## 📞 Soporte

Consulta la documentación completa en:
- [`NOTIFICACIONES_NO_LEIDOS.md`](NOTIFICACIONES_NO_LEIDOS.md) - Troubleshooting detallado
- [`DEPLOYMENT_NOTIFICACIONES.md`](DEPLOYMENT_NOTIFICACIONES.md) - Guía de deployment

---

**Versión**: 1.0  
**Fecha**: Enero 2026  
**Estado**: ✅ Completado y Listo para Producción
