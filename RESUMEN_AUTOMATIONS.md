# ✅ Sistema de Automatizaciones - Implementado

## 🎉 ¿Qué se creó?

He agregado un **sistema completo de automatizaciones** dentro de tu proyecto `hotboat-whatsapp` que te notifica por WhatsApp sobre eventos importantes.

## 📁 Estructura Nueva

```
hotboat-whatsapp/
├── automations/                     ← NUEVA CARPETA
│   ├── monitors/
│   │   ├── appointments_monitor.py  Monitor de reservas
│   │   └── stock_monitor.py         Monitor de inventario
│   ├── config.yaml                  Configuración
│   ├── notifications.py             Sistema de notificaciones
│   ├── database.py                  Utilidades BD
│   └── README.md                    Documentación
│
├── run_automations.py              ← SCRIPT PRINCIPAL
├── test_automations.py             ← SCRIPT DE PRUEBA
└── AUTOMATIONS_QUICKSTART.md       ← GUÍA RÁPIDA
```

## 🚀 Cómo Usar (3 pasos)

### 1. Instalar dependencia

```bash
pip install pyyaml
```

### 2. Agregar tu número en `.env`

Edita tu archivo `.env` y agrega al final:

```env
# Número para recibir notificaciones (sin + ni espacios)
AUTOMATION_PHONE_NUMBERS=56912345678
```

### 3. Ejecutar

```bash
python run_automations.py
```

**¡Listo!** Recibirás un mensaje de confirmación en tu WhatsApp.

## 📱 Notificaciones que Recibirás

### Nueva Reserva
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

### Reserva Modificada
```
ℹ️ 🔄 Reserva Modificada

👤 Cliente: Juan Pérez
📱 Teléfono: +56912345678

Cambios:
⏰ Hora: 10:00 → 14:00
👥 Personas: 4 → 6
```

### Reserva Cancelada
```
ℹ️ ❌ Reserva Cancelada

👤 Cliente: Juan Pérez
📅 Fecha: 05/11/2025
⏰ Hora: 14:00
💰 Monto: $50,000
```

### Stock Crítico (si usas inventario)
```
🚨 🔴 PRODUCTO SIN STOCK

📦 Producto: Botellas de Agua
🏷️ SKU: BEV-001
📊 Cantidad anterior: 8 unidades

⚠️ REQUIERE REPOSICIÓN URGENTE
```

## 🧪 Probar Ahora

Crea una reserva de prueba en tu base de datos:

```sql
INSERT INTO appointments (
    customer_name, phone_number, appointment_date, 
    start_time, boat_type, num_people, total_price
) VALUES (
    'Juan Pérez', '+56912345678', CURRENT_DATE + 1,
    '10:00', 'Lancha Rápida', 4, 50000
);
```

**En menos de 1 minuto recibirás la notificación en WhatsApp** 🎉

## ⚙️ Configuración

### Cambiar frecuencia de revisión

Edita `automations/config.yaml`:

```yaml
monitors:
  appointments:
    check_interval: 30  # Revisar cada 30 segundos
  
  stock:
    enabled: false  # Desactivar si no usas inventario
```

### Agregar más números

En `.env`:
```env
AUTOMATION_PHONE_NUMBERS=56912345678,56987654321,56911111111
```

### Ajustar prioridades

En `automations/config.yaml`:
```yaml
notifications:
  whatsapp:
    priority_levels:
      critical: true   # Stock crítico, errores
      high: true       # Nuevas reservas
      medium: false    # Modificaciones (desactivar)
      low: false
```

## 📚 Documentación

- **Guía rápida**: `AUTOMATIONS_QUICKSTART.md`
- **Documentación completa**: `automations/README.md`
- **Estructura del proyecto**: `automations/ESTRUCTURA.txt`

## 🔧 Scripts Útiles

```bash
# Probar configuración
python test_automations.py

# Ejecutar automatizaciones
python run_automations.py

# Ver logs
tail -f logs/app.log

# Windows PowerShell
Get-Content logs\app.log -Wait -Tail 50
```

## 🎯 Características

✅ **Usa tu WhatsApp ya configurado** - No necesitas tokens adicionales
✅ **Integrado en tu proyecto** - Todo en un solo lugar
✅ **Fácil de probar** - 3 comandos y ya funciona
✅ **Personalizable** - Ajusta intervalos, umbrales y prioridades
✅ **Extensible** - Fácil agregar nuevos monitores
✅ **Independiente** - Se ejecuta por separado del bot

## 💡 Casos de Uso

### Caso 1: Nueva Reserva
- Cliente hace reserva → Sistema detecta → Te notifica en WhatsApp

### Caso 2: Cliente Cambia Hora
- Cliente modifica reserva → Sistema detecta cambios → Te notifica

### Caso 3: Stock Bajo
- Usas inventario durante el día → Sistema detecta stock bajo → Te alerta

### Caso 4: Múltiples Usuarios
- Agrega números de tu equipo → Todos reciben notificaciones

## 🐛 Solución de Problemas

### No recibo mensajes
1. Verifica `AUTOMATION_PHONE_NUMBERS` en `.env` (sin `+` ni espacios)
2. Ejecuta `python test_automations.py` para diagnosticar
3. Revisa logs: `logs/app.log`

### "Tabla inventory no existe"
- Desactiva el monitor de stock en `automations/config.yaml`:
  ```yaml
  stock:
    enabled: false
  ```

### Error de conexión
- El sistema usa la misma BD que tu proyecto principal
- Verifica que `DATABASE_URL` esté correcta en `.env`

## 🔄 Ejecutar Junto con el Bot

Puedes ejecutar ambos simultáneamente:

**Terminal 1**: Bot de WhatsApp
```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**Terminal 2**: Automatizaciones
```bash
python run_automations.py
```

## 📊 Archivos Modificados

Solo se modificaron 3 archivos existentes:

1. **`app/config.py`** - Agregada variable `automation_phone_numbers`
2. **`env.example`** - Agregado ejemplo de configuración
3. **`requirements.txt`** - Agregada dependencia `pyyaml`

Todo lo demás es **nuevo** y **no afecta** tu código existente.

## 🎉 Ventajas de Esta Implementación

1. ✨ **Integrado**: Todo en un solo repositorio
2. ✨ **Reutiliza**: Usa tu WhatsApp y BD existentes
3. ✨ **Simple**: Solo 3 pasos para empezar
4. ✨ **Flexible**: Configurable y extensible
5. ✨ **Independiente**: No interfiere con el bot principal

## 🚀 ¡Empieza Ahora!

```bash
# 1. Instalar
pip install pyyaml

# 2. Configurar (edita .env)
echo "AUTOMATION_PHONE_NUMBERS=56912345678" >> .env

# 3. Probar
python test_automations.py

# 4. Ejecutar
python run_automations.py
```

**¿Preguntas?** 
- Lee `AUTOMATIONS_QUICKSTART.md` para la guía completa
- Lee `automations/README.md` para documentación detallada
- Revisa `automations/ESTRUCTURA.txt` para entender la estructura

---

**Creado:** 04 de noviembre de 2025
**Versión:** 1.0.0
**Estado:** ✅ Listo para usar

