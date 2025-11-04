# 🔧 ¿Para qué sirve `run_migrations.py`?

## 📋 Resumen

`run_migrations.py` crea las **tablas necesarias en tu base de datos PostgreSQL** para que el bot funcione correctamente.

## 🎯 ¿Qué hace exactamente?

Ejecuta SQL para crear estas 3 tablas:

### 1. **`whatsapp_leads`** - Contactos/Leads
Almacena información de los usuarios que contactan:
- Teléfono, nombre
- Estado del lead (potential_client, customer, etc.)
- Notas y tags
- Fechas de interacción

### 2. **`whatsapp_conversations`** - Historial de conversaciones
Guarda todas las conversaciones:
- Mensajes enviados y recibidos
- Respuestas del bot
- IDs de mensajes (para evitar duplicados)
- Timestamps

### 3. **`whatsapp_carts`** - Carritos de compra ✨ (NUEVO)
Almacena los carritos de los usuarios:
- Items en el carrito (reservas, extras)
- Datos en formato JSON
- Fechas de creación/actualización

## ❓ ¿Por qué tengo que correrlo?

Sin estas tablas, el bot **NO puede funcionar** porque:
- ❌ No puede guardar conversaciones
- ❌ No puede guardar carritos
- ❌ No puede gestionar leads
- ❌ Dará errores al intentar guardar datos

## 🚀 ¿Cuándo ejecutarlo?

### ✅ **SÍ necesitas ejecutarlo cuando:**

1. **Primera vez que configuras el bot**
   - Es la primera vez que usas esta base de datos
   - Necesitas crear las tablas desde cero

2. **Agregas nuevas funcionalidades**
   - Como el sistema de carrito (nueva tabla `whatsapp_carts`)
   - Cuando agregamos nuevas tablas

3. **Cambias de base de datos**
   - Si cambias de Railway a otra base de datos
   - Si usas una base de datos nueva

### ❌ **NO necesitas ejecutarlo cuando:**

1. **Ya ejecutaste las migraciones antes**
   - Las tablas ya existen
   - El script usa `CREATE TABLE IF NOT EXISTS` (no duplica)

2. **Solo estás haciendo cambios de código**
   - Cambios en la lógica del bot
   - Cambios en mensajes
   - No afectan la estructura de la base de datos

## 🎯 Opciones para ejecutarlo

### Opción 1: Desde tu computadora (Local) ✅ Recomendado para desarrollo

```bash
# 1. Configura tu .env con DATABASE_URL
# 2. Ejecuta:
python run_migrations.py
```

**Ventajas:**
- ✅ Fácil de probar localmente
- ✅ Puedes ver los mensajes de error claramente
- ✅ No afecta producción hasta que confirmes

### Opción 2: Desde Railway (Producción)

**Opción A: Railway CLI**
```bash
railway run python run_migrations.py
```

**Opción B: Desde Railway Dashboard**
1. Ve a tu proyecto en Railway
2. Click en tu servicio PostgreSQL
3. Click en "Query" o "Connect"
4. Pega el SQL de `create_carts_table.sql`

**Opción C: Automatizar en Railway**
Puedes crear un script que se ejecute automáticamente al hacer deploy.

## 📊 ¿Qué pasa si NO lo ejecuto?

Si no ejecutas las migraciones, verás errores como:

```
❌ Error: relation "whatsapp_carts" does not exist
❌ Error: table "whatsapp_leads" does not exist
❌ Error: column "message_id" does not exist
```

## 🔍 ¿Cómo verificar si ya está ejecutado?

Puedes verificar conectándote a tu base de datos:

```sql
-- Verificar si las tablas existen
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'public' 
AND table_name IN ('whatsapp_carts', 'whatsapp_leads', 'whatsapp_conversations');
```

Si ves las 3 tablas, ya están creadas ✅

## 💡 Recomendación

**Para desarrollo local:**
- Ejecuta `run_migrations.py` una vez al configurar
- No necesitas ejecutarlo cada vez que cambias código

**Para producción (Railway):**
- Ejecuta las migraciones una vez al configurar
- O configura un script que se ejecute automáticamente

## 🆘 Si tienes problemas

1. **Error de conexión:**
   - Verifica que `DATABASE_URL` esté correcto en `.env`
   - Verifica que la base de datos esté accesible

2. **Error de permisos:**
   - Asegúrate de que el usuario de PostgreSQL tenga permisos para crear tablas

3. **Tablas ya existen:**
   - No pasa nada, el script usa `IF NOT EXISTS`
   - Puedes ejecutarlo múltiples veces sin problemas

---

**En resumen:** `run_migrations.py` es como "preparar la base de datos" para que el bot pueda guardar información. Es como construir las estanterías antes de guardar libros. 📚

