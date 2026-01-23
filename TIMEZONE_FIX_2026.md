# 🕐 Fix de Timezone - Enero 2026

## 📋 Problema Identificado

**Fecha:** 23 de enero de 2026  
**Síntoma:** Los horarios de disponibilidad estaban corridos por **3 horas** más temprano de lo real.

### Ejemplo del problema:
- **Reserva real:** 14:00-16:00 (Nelson Valdebenito)
- **Sistema mostraba:** 11:00-13:00 ❌
- **Diferencia:** 3 horas de desfase

## 🔍 Causa Raíz

El plugin **Booknetic** (WordPress) guarda los timestamps con un error de timezone:

- **Guardado en DB:** `2026-01-24 14:00:00+00:00` (marcado como UTC)
- **Debería ser:** `2026-01-24 17:00:00+00:00` (UTC real para 14:00 Chile en verano)
- **Problema:** Guarda la hora LOCAL de Chile pero la marca como UTC

Cuando nuestro sistema leía estos timestamps:
1. PostgreSQL devuelve: `14:00:00+00:00` (marcado como UTC)
2. Python lo interpreta como UTC
3. Python convierte a Chile: `14:00 UTC - 3 horas = 11:00 Chile` ❌

## ✅ Solución Implementada

Modificamos `app/db/queries.py` para "corregir" el timezone de los timestamps:

### Cambios en `get_booked_slots()`:

```python
# FIX TIMEZONE ISSUE: 
# Booknetic stores timestamps with local Chile time but marks them as UTC
# We need to "fix" this by replacing the timezone
if starts_at and starts_at.tzinfo is not None:
    # Remove the UTC timezone and treat as naive
    naive_dt = starts_at.replace(tzinfo=None)
    # Re-apply Chile timezone (the actual timezone of the data)
    starts_at = CHILE_TZ.localize(naive_dt)
```

### Cambios en `check_slot_availability()`:

```python
# FIX TIMEZONE ISSUE:
# Since DB stores Chile time as UTC, we need to compare using naive datetimes
# Convert slot times to naive (removing timezone) for comparison
slot_start_naive = slot_start_with_buffer.replace(tzinfo=None)
slot_end_naive = slot_end_with_buffer.replace(tzinfo=None)
```

## 📊 Verificación

### Reservas reales para el 24 de enero de 2026:
1. **14:00-16:00** - Nelson Valdebenito (4 personas)
2. **16:00-18:00** - Josselyn Siares (2 personas)
3. **19:00-21:00** - Mariana Ferrer (2 personas)

### Horarios disponibles (correcto después del fix):
- ✅ **07:00** - Disponible
- ✅ **09:00** - Disponible
- ✅ **11:00** - Disponible
- ❌ **13:00** - Ocupado (se solapa con 14:00-16:00)
- ❌ **15:00** - Ocupado (se solapa con 14:00-16:00 y 16:00-18:00)
- ❌ **17:00** - Ocupado (se solapa con 16:00-18:00 y 19:00-21:00)
- ❌ **19:00** - Ocupado (reserva confirmada)
- ✅ **21:00** - Disponible

## 🚨 Importante para el Futuro

Este fix es una **solución temporal** al problema de Booknetic. Idealmente, se debería:

1. **Opción A:** Corregir cómo Booknetic guarda los timestamps
   - Configurar el plugin para usar correctamente UTC
   - O configurar para guardar explícitamente en timezone de Chile

2. **Opción B:** Migrar los datos existentes
   - Corregir todos los timestamps existentes en la DB
   - Actualizar `starts_at` para reflejar UTC real

3. **Opción C:** Si este fix funciona correctamente
   - Mantenerlo como está y documentar el comportamiento
   - Asegurar que cualquier código nuevo que escriba a la DB también use este formato

## 📝 Archivos Modificados

- `app/db/queries.py` - Funciones `get_booked_slots()` y `check_slot_availability()`

## 🧪 Testing

Para verificar que el fix funciona:

```python
python test_timezone_fix.py
```

El test debe mostrar los horarios correctos según las reservas reales.

---

**Autor:** Sistema de disponibilidad HotBoat  
**Fecha:** 23 de enero de 2026  
**Estado:** ✅ Resuelto y verificado
