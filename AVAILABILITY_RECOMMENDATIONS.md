# 📅 Sistema de Disponibilidad - Recomendaciones y Documentación

## ✅ Lo que hemos implementado

He mejorado completamente el sistema de disponibilidad para que pueda entender y mostrar correctamente los horarios disponibles a los clientes por WhatsApp.

### 🎯 Características principales

1. **Configuración centralizada** (`app/availability/availability_config.py`)
   - Horarios de operación: 10:00, 12:00, 14:00, 16:00, 18:00, 19:00
   - Duración de cada viaje: 2 horas
   - Buffer entre reservas: 30 minutos
   - Servicios con capacidades (2-7 personas)

2. **Cálculo inteligente de disponibilidad**
   - Consulta la base de datos en tiempo real
   - Considera la duración de cada viaje (2 horas)
   - Evita overlaps con buffer de 30 minutos
   - Filtra appointments cancelados

3. **Respuestas claras al cliente**
   - Muestra disponibilidad por día con horarios específicos
   - Formato en español y fácil de leer
   - Sugiere próximos pasos

## 📊 Estructura de datos actual

### Tabla `booknetic_appointments`
- **id**: Identificador único
- **customer_name**: Nombre del cliente
- **customer_email**: Email del cliente
- **service_name**: Nombre del servicio (ej: "HotBoat Trip 2 people")
- **starts_at**: Fecha y hora del appointment (timestamp with timezone)
- **status**: Estado del appointment (NULL = confirmado/pending)
- **raw**: Datos adicionales en JSONB

### Observaciones importantes
1. **Status NULL**: Los appointments con `status = NULL` se consideran como confirmados/pending
2. **Timezone**: Los appointments están en UTC, el sistema los convierte a hora de Chile
3. **Horarios variables**: Los appointments pueden tener cualquier hora, pero el sistema solo muestra disponibilidad en los horarios de operación configurados (10, 12, 14, 16, 18, 19)

## 💡 Recomendaciones para mejorar los datos

### 1. **Normalizar horarios de reserva**
Actualmente los appointments pueden tener cualquier hora. Recomiendo:

```sql
-- Ver horarios no estándar
SELECT 
    EXTRACT(HOUR FROM starts_at) as hora,
    COUNT(*) as cantidad
FROM booknetic_appointments
WHERE starts_at >= NOW()
GROUP BY EXTRACT(HOUR FROM starts_at)
ORDER BY hora;
```

**Sugerencia**: Forzar que las reservas solo puedan hacerse en horarios estándar (10, 12, 14, 16, 18, 19) desde Booknetic.

### 2. **Mejorar el campo status**
Actualmente muchos appointments tienen `status = NULL`. Recomiendo:

- Usar valores específicos: `'confirmed'`, `'pending'`, `'cancelled'`, `'completed'`
- Si NULL significa "confirmado", considerar un valor por defecto
- Esto ayudará a filtrar mejor la disponibilidad

### 3. **Agregar campo de duración**
Si diferentes servicios tienen diferentes duraciones, considera:

```sql
ALTER TABLE booknetic_appointments 
ADD COLUMN duration_hours DECIMAL(3,1) DEFAULT 2.0;
```

Esto permitirá calcular mejor los overlaps.

### 4. **Tabla de servicios/horarios**
Para mayor flexibilidad, considera crear una tabla de configuración:

```sql
CREATE TABLE service_schedules (
    id SERIAL PRIMARY KEY,
    service_name VARCHAR(255),
    capacity_min INTEGER,
    capacity_max INTEGER,
    duration_hours DECIMAL(3,1),
    operating_hours INTEGER[],  -- Array de horas [10, 12, 14, 16, 18, 19]
    is_active BOOLEAN DEFAULT TRUE
);
```

## 🔧 Cómo funciona el sistema

### Flujo de consulta de disponibilidad

1. **Cliente pregunta**: "¿Tienen disponibilidad?"
2. **Sistema parsea la fecha**:
   - "mañana" → próximo día
   - "próxima semana" → 7 días
   - "mes" → 30 días
   - Por defecto → 7 días

3. **Consulta base de datos**:
   - Obtiene todos los appointments en el rango
   - Filtra cancelados/rechazados
   - Considera NULL como confirmado

4. **Calcula slots disponibles**:
   - Genera todos los posibles horarios (10, 12, 14, 16, 18, 19) para cada día
   - Verifica overlaps considerando duración (2h) + buffer (30min)
   - Filtra slots en el pasado

5. **Formatea respuesta**:
   - Agrupa por fecha
   - Muestra horarios disponibles por día
   - Sugiere próximos pasos

### Ejemplo de respuesta

```
✅ ¡Tenemos disponibilidad!

📅 Domingo 02/11/2025: 12:00, 14:00, 16:00, 18:00, 19:00
📅 Lunes 03/11/2025: 10:00, 12:00, 14:00, 16:00, 18:00, 19:00
📅 Martes 04/11/2025: 10:00, 12:00, 14:00, 16:00, 18:00, 19:00
...

👥 ¿Para cuántas personas sería?
Puedo ayudarte a reservar el horario perfecto.

💡 También puedes reservar directamente aquí:
https://hotboatchile.com/es/book-hotboat/
```

## 🚀 Próximos pasos sugeridos

### Corto plazo
1. ✅ Sistema de disponibilidad implementado y funcionando
2. ⏳ Probar en producción con clientes reales
3. ⏳ Ajustar horarios de operación si es necesario

### Medio plazo
1. **Integración con Booknetic API**: Si Booknetic tiene API, sincronizar en tiempo real
2. **Notificaciones**: Alertar cuando alguien reserva un slot que estaba disponible
3. **Reservas directas**: Permitir reservar desde WhatsApp (si Booknetic API lo permite)

### Largo plazo
1. **Análisis de demanda**: Ver qué horarios son más populares
2. **Precios dinámicos**: Ajustar precios según demanda
3. **Calendario visual**: Enviar calendario interactivo por WhatsApp

## 🧪 Testing

Puedes probar el sistema con:

```bash
python test_availability.py
```

Este script prueba:
- Consulta general de disponibilidad
- Disponibilidad para mañana
- Obtención de slots disponibles

## 📝 Configuración personalizada

Puedes ajustar los horarios de operación en `app/availability/availability_config.py`:

```python
AVAILABILITY_CONFIG = AvailabilityConfig(
    operating_hours=[9, 12, 15, 18, 21, 00],  # Cambia estos horarios
    duration_hours=2.0,  # Duración de cada viaje
    buffer_hours=1,  # Buffer entre reservas (30 min)
    exclude_statuses=['cancelled', 'rejected']
)
```

## ✅ Resumen

El sistema ahora:
- ✅ Consulta la base de datos en tiempo real
- ✅ Calcula disponibilidad considerando duración y overlaps
- ✅ Muestra respuestas claras y útiles al cliente
- ✅ Maneja diferentes tipos de consultas (mañana, semana, mes)
- ✅ Filtra appointments cancelados
- ✅ Usa timezone de Chile correctamente

**El sistema está listo para usar y ayudará a tus clientes a encontrar disponibilidad de manera clara y eficiente!** 🎉




