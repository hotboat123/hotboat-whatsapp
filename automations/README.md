# 🤖 Sistema de Automatizaciones HotBoat

Sistema de monitoreo automático que te notifica por WhatsApp sobre eventos importantes en tu negocio.

## 🎯 ¿Qué hace?

### Monitor de Reservas (Appointments)
- ✅ Te avisa cuando hay una **nueva reserva**
- ✅ Te notifica si se **cancela** una reserva
- ✅ Te alerta sobre **modificaciones** en reservas existentes

### Monitor de Stock (Inventario)
- ✅ Alerta de **stock bajo**
- ✅ Alerta de **stock crítico**
- ✅ Alerta de **producto sin stock**
- ✅ Notifica cuando se **repone stock**

## 📱 Notificaciones por WhatsApp

Todas las notificaciones llegan directamente a tu WhatsApp usando el mismo sistema que ya tienes configurado.

## 🚀 Configuración Rápida (3 pasos)

### 1. Agregar números de teléfono

Edita tu archivo `.env` y agrega esta línea:

```env
# Números para notificaciones de automatización (sin + ni espacios, separados por coma)
AUTOMATION_PHONE_NUMBERS=56912345678,56987654321
```

**Importante:** Los números deben estar en formato internacional **sin** el símbolo `+` y **sin espacios**.
- ✅ Correcto: `56912345678`
- ❌ Incorrecto: `+56 9 1234 5678`

### 2. Actualizar app/config.py

Agrega esta línea en la clase `Settings` (alrededor de la línea 50):

```python
class Settings(BaseSettings):
    # ... (otras configuraciones)
    
    # Automations
    automation_phone_numbers: str = ""  # ← Agrega esta línea
```

### 3. Ejecutar

```bash
python run_automations.py
```

¡Listo! Recibirás un mensaje de confirmación en WhatsApp.

## 🧪 Probar el Sistema

### Probar Monitor de Reservas

Crea una nueva reserva en tu base de datos:

```sql
INSERT INTO appointments (
    customer_name, phone_number, appointment_date, 
    start_time, boat_type, num_people, total_price
) VALUES (
    'Juan Pérez', '+56912345678', CURRENT_DATE + 1,
    '10:00', 'Lancha Rápida', 4, 50000
);
```

**Resultado:** Recibirás en WhatsApp:
```
⚠️ 🎉 Nueva Reserva Creada

👤 Cliente: Juan Pérez
📱 Teléfono: +56912345678
📅 Fecha: 05/11/2025
⏰ Hora: 10:00
⛵ Embarcación: Lancha Rápida
👥 Personas: 4
💰 Total: $50,000
```

### Probar Monitor de Stock (Opcional)

Primero, crea la tabla de inventario:

```bash
# Ejecuta este archivo SQL en tu base de datos:
# automations/setup_inventory.sql
```

Luego, actualiza el stock:

```sql
UPDATE inventory 
SET quantity = 1 
WHERE product_name = 'Botellas de Agua';
```

**Resultado:** Recibirás alerta de stock crítico en WhatsApp.

## ⚙️ Configuración Avanzada

Edita `automations/config.yaml` para personalizar:

```yaml
monitors:
  appointments:
    enabled: true
    check_interval: 60  # Revisar cada 60 segundos
  
  stock:
    enabled: true  # Cambia a false si no usas inventario
    check_interval: 300  # Revisar cada 5 minutos
    thresholds:
      low_stock: 5
      critical_stock: 2

notifications:
  whatsapp:
    priority_levels:
      critical: true
      high: true
      medium: true
      low: false  # No enviar notificaciones de baja prioridad
```

## 📊 Ejemplos de Notificaciones

### Nueva Reserva
```
⚠️ 🎉 Nueva Reserva Creada

👤 Cliente: María González
📱 Teléfono: +56987654321
📅 Fecha: 15/11/2025
⏰ Hora: 14:00
⛵ Embarcación: Lancha Deportiva
👥 Personas: 6
💰 Total: $80,000
```

### Reserva Modificada
```
ℹ️ 🔄 Reserva Modificada

👤 Cliente: María González
📱 Teléfono: +56987654321

Cambios:
📅 Fecha: 15/11/2025 → 16/11/2025
⏰ Hora: 14:00 → 16:00
```

### Stock Crítico
```
🚨 🔴 PRODUCTO SIN STOCK

📦 Producto: Botellas de Agua
🏷️ SKU: BEV-001
📊 Cantidad anterior: 8 unidades

⚠️ REQUIERE REPOSICIÓN URGENTE
```

## 🔧 Comandos Útiles

```bash
# Iniciar automatizaciones
python run_automations.py

# Ver solo los logs de automatizaciones
tail -f logs/app.log | grep "automation"

# En Windows PowerShell:
Get-Content logs\app.log -Wait -Tail 50
```

## 🐛 Solución de Problemas

### No recibo notificaciones

1. **Verifica que configuraste AUTOMATION_PHONE_NUMBERS en .env**
   ```bash
   # Formato correcto:
   AUTOMATION_PHONE_NUMBERS=56912345678
   ```

2. **Verifica que agregaste el campo en app/config.py**
   ```python
   automation_phone_numbers: str = ""
   ```

3. **Verifica los logs**
   ```bash
   # Busca errores en los logs
   cat logs/app.log | grep ERROR
   ```

4. **El número debe ser el mismo formato que usas en WhatsApp Business API**
   - Sin `+`
   - Sin espacios
   - Con código de país

### Error: "tabla inventory no existe"

Si no usas el monitor de stock, desactívalo en `automations/config.yaml`:

```yaml
monitors:
  stock:
    enabled: false  # ← Cambia a false
```

O ejecuta `automations/setup_inventory.sql` para crear la tabla.

### Error de conexión a base de datos

El sistema usa la misma conexión que tu proyecto principal. Verifica que `DATABASE_URL` esté correctamente configurada en `.env`.

## 📁 Estructura de Archivos

```
automations/
├── __init__.py
├── config.yaml              # Configuración de monitores
├── database.py              # Utilidades de BD
├── notifications.py         # Sistema de notificaciones WhatsApp
├── setup_inventory.sql      # Script para crear tabla inventory
├── README.md               # Este archivo
└── monitors/
    ├── __init__.py
    ├── base_monitor.py     # Clase base
    ├── appointments_monitor.py  # Monitor de reservas
    └── stock_monitor.py    # Monitor de inventario
```

## 🔄 Ejecutar Junto con el Bot Principal

Puedes ejecutar ambos sistemas simultáneamente:

```bash
# Terminal 1: Bot de WhatsApp
python -m uvicorn app.main:app --reload

# Terminal 2: Automatizaciones
python run_automations.py
```

O usar un process manager como `pm2` o `supervisor`.

## 🎯 Prioridades

- **Critical (🚨)**: Stock en 0, errores del sistema
- **High (⚠️)**: Nueva reserva, stock crítico, reserva cancelada
- **Medium (ℹ️)**: Reserva modificada, stock bajo
- **Low (💬)**: Stock restaurado, info general

Puedes ajustar qué prioridades recibes en `config.yaml`.

## 💡 Tips

1. **Empieza con el monitor de reservas** - Es el más útil
2. **Ajusta los intervalos** según tu volumen de datos
3. **Prueba primero con un solo número** antes de agregar varios
4. **Revisa los logs** si algo no funciona como esperas

## 🚀 Próximos Pasos

- Agrega más monitores personalizados
- Crea alertas de mantenimiento de embarcaciones
- Integra con tu sistema de pagos
- Configura resúmenes diarios

¡Disfruta de tus automatizaciones! 🎉

