# 🤖 Guía Rápida: Automatizaciones HotBoat

Sistema que te notifica por WhatsApp sobre eventos importantes en tu negocio.

## 🚀 Configuración (3 minutos)

### Paso 1: Agregar tu número de WhatsApp

Edita tu archivo `.env` y agrega:

```env
# Al final del archivo .env, agrega esta línea:
AUTOMATION_PHONE_NUMBERS=56912345678
```

**⚠️ Importante:**
- **SIN** el símbolo `+`
- **SIN** espacios
- Formato: código de país + número
- Para múltiples números: `56912345678,56987654321`

### Paso 2: Instalar dependencia (si no la tienes)

```bash
pip install pyyaml
```

### Paso 3: Ejecutar

```bash
python run_automations.py
```

✅ Recibirás un mensaje de confirmación en WhatsApp diciendo:
```
ℹ️ ✅ Sistema de automatizaciones HotBoat iniciado correctamente
```

---

## 🧪 Probar Ahora Mismo

### Prueba 1: Nueva Reserva

Abre tu cliente PostgreSQL (DBeaver, pgAdmin, etc.) y ejecuta:

```sql
INSERT INTO appointments (
    customer_name, 
    phone_number, 
    appointment_date, 
    start_time, 
    boat_type, 
    num_people, 
    total_price
) VALUES (
    'Juan Pérez',
    '+56912345678',
    CURRENT_DATE + 1,
    '10:00',
    'Lancha Rápida',
    4,
    50000
);
```

**En 1 minuto recibirás en WhatsApp:**

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

### Prueba 2: Modificar Reserva

```sql
UPDATE appointments 
SET start_time = '14:00', num_people = 6
WHERE customer_name = 'Juan Pérez'
AND appointment_date = CURRENT_DATE + 1;
```

**Recibirás:**
```
ℹ️ 🔄 Reserva Modificada

👤 Cliente: Juan Pérez
📱 Teléfono: +56912345678

Cambios:
⏰ Hora: 10:00 → 14:00
👥 Personas: 4 → 6
```

### Prueba 3: Cancelar Reserva

```sql
DELETE FROM appointments 
WHERE customer_name = 'Juan Pérez'
AND appointment_date = CURRENT_DATE + 1;
```

**Recibirás:**
```
ℹ️ ❌ Reserva Cancelada

👤 Cliente: Juan Pérez
📅 Fecha: 05/11/2025
⏰ Hora: 14:00
💰 Monto: $50,000
```

---

## ⚙️ Personalizar (Opcional)

### Cambiar frecuencia de revisión

Edita `automations/config.yaml`:

```yaml
monitors:
  appointments:
    check_interval: 30  # Revisar cada 30 segundos (en lugar de 60)
```

### Desactivar notificaciones de prioridad media

```yaml
notifications:
  whatsapp:
    priority_levels:
      critical: true  # Stock crítico, errores
      high: true      # Nuevas reservas
      medium: false   # Modificaciones (desactivado)
      low: false
```

### Desactivar el monitor de stock

Si no usas inventario:

```yaml
monitors:
  stock:
    enabled: false  # Desactivar
```

---

## 📦 Monitor de Stock (Opcional)

Si quieres monitorear tu inventario:

### 1. Crear la tabla

Ejecuta en PostgreSQL:

```sql
-- Ver archivo: automations/setup_inventory.sql
CREATE TABLE inventory (
    id SERIAL PRIMARY KEY,
    product_name VARCHAR(255) NOT NULL,
    sku VARCHAR(100) UNIQUE,
    category VARCHAR(100),
    quantity INTEGER NOT NULL DEFAULT 0,
    unit VARCHAR(50) DEFAULT 'unidades',
    min_stock INTEGER DEFAULT 5
);

-- Agregar algunos productos
INSERT INTO inventory (product_name, sku, category, quantity, unit, min_stock)
VALUES 
    ('Chalecos Salvavidas', 'SAFE-001', 'Seguridad', 15, 'unidades', 10),
    ('Combustible', 'FUEL-001', 'Combustible', 50, 'litros', 100),
    ('Botellas de Agua', 'BEV-001', 'Bebidas', 8, 'unidades', 20);
```

### 2. Probar

```sql
-- Simular stock bajo
UPDATE inventory SET quantity = 3 WHERE sku = 'BEV-001';
```

**Recibirás en WhatsApp:**
```
ℹ️ 🟡 Stock Bajo

📦 Producto: Botellas de Agua
📊 Cantidad: 3 unidades
📌 Stock mínimo: 20

ℹ️ Considera reabastecer
```

---

## 🛠️ Comandos

```bash
# Iniciar
python run_automations.py

# Detener
Ctrl + C

# Ver logs
tail -f logs/app.log

# Windows PowerShell
Get-Content logs\app.log -Wait -Tail 50
```

---

## 🐛 Problemas Comunes

### "No hay destinatarios configurados"

✅ **Solución:** Verifica que agregaste `AUTOMATION_PHONE_NUMBERS` en tu `.env`

### "No recibo mensajes"

1. Verifica que el número esté en el formato correcto (sin `+` ni espacios)
2. Verifica que el bot de WhatsApp esté ejecutándose (`python -m uvicorn app.main:app`)
3. Revisa los logs: `logs/app.log`

### "Tabla inventory no existe"

✅ **Solución 1:** Desactiva el monitor de stock en `automations/config.yaml`:
```yaml
stock:
  enabled: false
```

✅ **Solución 2:** Crea la tabla ejecutando `automations/setup_inventory.sql`

---

## 📊 ¿Qué notificaciones recibirás?

### 🎉 Nueva Reserva (High Priority)
Cada vez que alguien hace una reserva

### 🔄 Reserva Modificada (Medium Priority)
Cuando cambia fecha, hora o número de personas

### ❌ Reserva Cancelada (Medium Priority)
Cuando se elimina una reserva

### 🟡 Stock Bajo (Medium Priority)
Cuando un producto llega al stock mínimo

### 🟠 Stock Crítico (High Priority)
Cuando un producto tiene muy pocas unidades

### 🔴 Sin Stock (Critical Priority)
Cuando un producto se agota completamente

---

## 💡 Tips

1. **Empieza solo con reservas** - Es lo más útil
2. **Prueba con tu número primero** antes de agregar otros
3. **Ajusta el intervalo** según tu volumen (default: 60 segundos)
4. **Revisa los logs** si algo no funciona

---

## 🔄 Ejecutar Junto con el Bot

Puedes tener ambos corriendo al mismo tiempo:

**Terminal 1:** Bot de WhatsApp
```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**Terminal 2:** Automatizaciones
```bash
python run_automations.py
```

---

## 📱 Ejemplo Real

Imagina este escenario:

1. **10:30 AM** - Un cliente hace una reserva en tu sistema
2. **10:31 AM** - Recibes notificación en WhatsApp
3. **11:00 AM** - El cliente cambia la hora
4. **11:01 AM** - Recibes notificación del cambio
5. **Durante el día** - Revisas tu stock y ves que tienes pocas toallas
6. **15:00 PM** - El sistema te alerta automáticamente

**Todo sin que tengas que revisar manualmente** ✨

---

## 🎯 Próximos Pasos

Una vez que lo tengas funcionando:

1. ✅ Agrega más números de tu equipo
2. ✅ Personaliza los mensajes editando los archivos en `automations/monitors/`
3. ✅ Crea monitores personalizados para tus necesidades específicas
4. ✅ Configura para que se ejecute automáticamente al iniciar el servidor

---

## 📚 Más Información

- Ver documentación completa: `automations/README.md`
- Ver ejemplos de código: Archivos en `automations/monitors/`
- Ver configuración: `automations/config.yaml`

---

**¿Listo para empezar?** 🚀

1. Edita `.env` y agrega tu número
2. Ejecuta `python run_automations.py`
3. ¡Listo! Ya estás recibiendo notificaciones automáticas

¿Preguntas? Revisa `automations/README.md` o los logs en `logs/app.log`

