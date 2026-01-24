# 🚀 Guía de Deployment - Sistema de Notificaciones No Leídos

## 📋 Pre-requisitos

- ✅ Acceso a la base de datos (PostgreSQL)
- ✅ Acceso al servidor donde corre la aplicación
- ✅ Backup de la base de datos (recomendado)

## 🔧 Pasos de Deployment

### Paso 1: Backup de Base de Datos (Recomendado)

```bash
# Crear backup antes de la migración
pg_dump $DATABASE_URL > backup_before_unread_$(date +%Y%m%d_%H%M%S).sql
```

### Paso 2: Ejecutar Migración

**Opción A: Script automático (Recomendado)**

```bash
# Desde el directorio raíz del proyecto
python run_migration_008.py
```

**Opción B: SQL directo**

```bash
# Conectar a la base de datos y ejecutar:
psql $DATABASE_URL -f migrations/008_add_unread_count.sql
```

**Opción C: Script general de migraciones**

```bash
python run_migrations.py
```

### Paso 3: Verificar Migración

```bash
# Ejecutar test
python test_unread_notifications.py
```

Deberías ver algo como:

```
🧪 Testing Unread Notifications System

1️⃣ Creating/getting test lead...
   ✅ Lead: Test User (56999999999)
   📊 Initial unread_count: 0

2️⃣ Simulating incoming messages...
   ✅ Message 1 received - counter incremented
   ✅ Message 2 received - counter incremented
   ✅ Message 3 received - counter incremented

3️⃣ Checking updated count...
   📊 Current unread_count: 3
   ✅ Counter is correct!

...
```

### Paso 4: Reiniciar Aplicación

**En Railway/Heroku:**

```bash
# Railway
railway restart

# Heroku
heroku restart
```

**En servidor local/VPS:**

```bash
# Detener proceso actual (Ctrl+C si está en primer plano)
# O si está como servicio:
sudo systemctl restart hotboat-whatsapp

# O con PM2:
pm2 restart hotboat-whatsapp
```

### Paso 5: Verificar Frontend

1. Abre Kia-Ai en el navegador: https://tu-dominio.com
2. Abre la consola del navegador (F12)
3. Refresca la página (Ctrl+R o Cmd+R)
4. No deberían aparecer errores en la consola

### Paso 6: Prueba End-to-End

1. **Enviar mensaje de prueba**:
   - Envía un mensaje desde WhatsApp a tu número de bot
   - Espera 10-15 segundos (tiempo de refresh)

2. **Verificar badge**:
   - Abre Kia-Ai
   - Busca la conversación en la lista
   - Debe aparecer un badge verde con el número "1"

3. **Probar marca como leído**:
   - Click en la conversación
   - El badge debe desaparecer inmediatamente
   - Sal y vuelve a la lista
   - El badge NO debe reaparecer

## ✅ Checklist de Deployment

```
[ ] Backup de base de datos creado
[ ] Migración SQL ejecutada sin errores
[ ] Columnas unread_count y last_read_at verificadas
[ ] Test script ejecutado exitosamente
[ ] Aplicación reiniciada
[ ] Frontend carga sin errores
[ ] Badge aparece en conversaciones con mensajes nuevos
[ ] Badge desaparece al abrir conversación
```

## 🔍 Troubleshooting

### Error: "column unread_count does not exist"

**Causa**: La migración no se ejecutó correctamente.

**Solución**:

```bash
# Verificar si la columna existe
psql $DATABASE_URL -c "SELECT column_name FROM information_schema.columns WHERE table_name = 'whatsapp_leads' AND column_name = 'unread_count';"

# Si no existe, ejecutar migración manualmente
psql $DATABASE_URL -f migrations/008_add_unread_count.sql
```

### Error: "Failed to mark conversation as read"

**Causa**: Problema de conexión a BD o lead no existe.

**Solución**:

```bash
# Verificar que el lead existe
psql $DATABASE_URL -c "SELECT phone_number, unread_count FROM whatsapp_leads WHERE phone_number = '56XXXXXXXXX';"

# Si no existe, el sistema lo creará automáticamente al recibir el próximo mensaje
```

### Badge no aparece en frontend

**Causa**: Cache del navegador o versión antigua del JS.

**Solución**:

1. Hard refresh: Ctrl+Shift+R (Windows/Linux) o Cmd+Shift+R (Mac)
2. Borrar cache del navegador
3. Verificar que el archivo app.js se actualizó:
   ```bash
   grep "unread-indicator" app/static/app.js
   grep "markConversationAsRead" app/static/app.js
   ```

### Contador incorrecto

**Causa**: Mensajes procesados antes de la migración.

**Solución**:

```sql
-- Resetear todos los contadores a 0
UPDATE whatsapp_leads SET unread_count = 0, last_read_at = NULL;

-- El sistema empezará a contar desde ahora
```

## 📊 Monitoreo Post-Deployment

### Verificar logs

```bash
# Buscar incrementos de contador
grep "Incremented unread count" logs/app.log | tail -20

# Buscar marcas como leído
grep "Marked conversation as read" logs/app.log | tail -20

# Buscar errores relacionados
grep "unread" logs/app.log | grep -i error
```

### Consultas útiles

```sql
-- Ver todas las conversaciones con mensajes no leídos
SELECT 
    phone_number, 
    customer_name, 
    unread_count, 
    last_read_at
FROM whatsapp_leads
WHERE unread_count > 0
ORDER BY unread_count DESC;

-- Estadísticas generales
SELECT 
    COUNT(*) as total_leads,
    SUM(CASE WHEN unread_count > 0 THEN 1 ELSE 0 END) as leads_with_unread,
    SUM(unread_count) as total_unread_messages,
    AVG(CASE WHEN unread_count > 0 THEN unread_count ELSE NULL END) as avg_unread_per_lead
FROM whatsapp_leads;
```

## 🔄 Rollback (Si es necesario)

Si algo sale mal y necesitas revertir:

```sql
-- Eliminar las columnas agregadas
ALTER TABLE whatsapp_leads 
DROP COLUMN IF EXISTS unread_count,
DROP COLUMN IF EXISTS last_read_at;

-- Revertir código (hacer git revert de los commits)
git revert <commit-hash>
```

## 📞 Soporte

Si encuentras problemas:

1. Revisa los logs del servidor
2. Consulta `NOTIFICACIONES_NO_LEIDOS.md` para troubleshooting detallado
3. Ejecuta `test_unread_notifications.py` para diagnóstico
4. Verifica la base de datos con las queries de monitoreo

---

**Última actualización**: Enero 2026
**Versión del sistema**: 1.0
