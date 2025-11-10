# 🔄 Flujo Completo: Consulta de Disponibilidad en WhatsApp

## 📊 Diagrama del Flujo

```
Usuario envía mensaje en WhatsApp
         ↓
WhatsApp Business API recibe webhook
         ↓
app/whatsapp/webhook.py → handle_webhook()
         ↓
Extrae mensaje y contact info
         ↓
app/whatsapp/webhook.py → process_message()
         ↓
Envía a ConversationManager
         ↓
app/bot/conversation.py → process_message()
         ↓
¿Es consulta de disponibilidad?
    (is_availability_query)
         ↓ SÍ
app/bot/availability.py → check_availability()
         ↓
Parsea fecha del mensaje
    (_parse_spanish_date)
         ↓
Calcula rango de fechas
    (start_date, end_date)
         ↓
app/bot/availability.py → get_available_slots()
         ↓
app/db/queries.py → get_booked_slots()
    (consulta PostgreSQL)
         ↓
Calcula slots disponibles
    (considerando buffer times)
         ↓
Formatea respuesta amigable
         ↓
Envía respuesta por WhatsApp
         ↓
Guarda conversación en DB
```

---

## 🔍 Detalle Paso a Paso

### **Paso 1: Recepción del Webhook** 
📁 `app/whatsapp/webhook.py`

**Endpoint:** `POST /webhook`

```python
async def handle_webhook(body, conversation_manager):
    # WhatsApp envía datos en esta estructura
    entries = body.get("entry", [])
    
    for entry in entries:
        changes = entry.get("changes", [])
        
        for change in changes:
            messages = change.get("value", {}).get("messages", [])
            
            for message in messages:
                await process_message(message, value, conversation_manager)
```

**Extrae:**
- `from_number`: Número de teléfono del usuario
- `text_body`: Texto del mensaje
- `contact_name`: Nombre del contacto
- `message_id`: ID único del mensaje

---

### **Paso 2: Procesamiento del Mensaje**
📁 `app/whatsapp/webhook.py` → `process_message()`

```python
# Marca mensaje como leído
await whatsapp_client.mark_as_read(message_id)

# Procesa el mensaje con ConversationManager
response = await conversation_manager.process_message(
    from_number=from_number,
    message_text=text_body,
    contact_name=contact_name,
    message_id=message_id
)

# Envía respuesta
if response:
    await whatsapp_client.send_text_message(from_number, response)
```

---

### **Paso 3: Decisión del Tipo de Mensaje**
📁 `app/bot/conversation.py` → `process_message()`

**Flujo de decisión:**

```python
# 1. ¿Es primer mensaje? → Mensaje de bienvenida POPEYE
if is_first:
    response = """🥬 ¡Ahoy, grumete! ⚓ Soy Popeye el Marino..."""

# 2. ¿Es pregunta FAQ? → Respuesta predefinida
elif self.faq_handler.get_response(message_text):
    response = self.faq_handler.get_response(message_text)

# 3. ¿Es consulta de disponibilidad? → CHECK AVAILABILITY
elif self.is_availability_query(message_text):
    response = await self.availability_checker.check_availability(message_text)

# 4. ¿Otra cosa? → Respuesta con IA
else:
    response = await self.ai_handler.generate_response(...)
```

---

### **Paso 4: Detección de Consulta de Disponibilidad**
📁 `app/bot/conversation.py` → `is_availability_query()`

**Método de detección:**

```python
def is_availability_query(self, message: str) -> bool:
    message_lower = message.lower()
    
    # Palabras clave tradicionales
    keywords = [
        "disponibilidad", "disponible", "horario", 
        "cuándo", "fecha", "reservar", "agendar",
        "mañana", "tomorrow", "hoy", "today"
    ]
    
    if any(keyword in message_lower for keyword in keywords):
        return True
    
    # Detecta fechas (sin necesidad de decir "disponibilidad")
    if self._contains_date(message):
        return True  # "14 de febrero" también activa disponibilidad
    
    return False
```

**Ejemplos que activan:**
- ✅ "¿Tienen disponibilidad?"
- ✅ "disponibilidad mañana"
- ✅ "14 de febrero" (solo la fecha)
- ✅ "quiero reservar"
- ✅ "¿qué horarios tienen?"

---

### **Paso 5: Procesamiento de Disponibilidad**
📁 `app/bot/availability.py` → `check_availability()`

**Proceso:**

```python
async def check_availability(self, message: str) -> str:
    # 1. Obtiene hora actual (Chile timezone)
    now = datetime.now(CHILE_TZ)
    
    # 2. Parsea fecha del mensaje
    specific_date = self._parse_spanish_date(message, current_year)
    
    if specific_date:
        # Fecha específica: "14 de febrero"
        start_date = specific_date.replace(hour=0, minute=0)
        end_date = specific_date.replace(hour=23, minute=59)
    elif "mañana" in message:
        # Mañana: solo el día siguiente
        tomorrow = now + timedelta(days=1)
        start_date = tomorrow.replace(hour=0, minute=0)
        end_date = tomorrow.replace(hour=23, minute=59)
    else:
        # Por defecto: próximos 7 días
        start_date = now
        end_date = now + timedelta(days=7)
    
    # 3. Obtiene slots disponibles
    available_slots = await self.get_available_slots(start_date, end_date)
    
    # 4. Formatea respuesta
    return format_availability_response(available_slots)
```

---

### **Paso 6: Parsing de Fechas en Español**
📁 `app/bot/availability.py` → `_parse_spanish_date()`

**Patrones reconocidos:**

```python
# Pattern 1: "14 de febrero"
r'(\d{1,2})\s+de\s+(enero|febrero|marzo|...)'

# Pattern 2: "febrero 14"
r'(enero|febrero|marzo|...)\s+(\d{1,2})'

# Pattern 3: "14 febrero"
r'(\d{1,2})\s+(enero|febrero|marzo|...)'

# Pattern 4: "14/02", "18/11"
r'(\d{1,2})[/-](\d{1,2})'
```

**Manejo de año:**
- Si la fecha está en el pasado → usa año siguiente
- Si está en el futuro → usa año actual

---

### **Paso 7: Cálculo de Slots Disponibles**
📁 `app/bot/availability.py` → `get_available_slots()`

**Configuración** (`app/availability/availability_config.py`):

```python
AVAILABILITY_CONFIG = AvailabilityConfig(
    operating_hours=[9, 12, 15, 18, 21],  # Horarios disponibles
    duration_hours=2.0,                    # Duración del tour
    buffer_hours=1.0,                     # Buffer antes/después
    excluded_statuses=['cancelled', 'rejected']
)
```

**Proceso:**

```python
async def get_available_slots(start_date, end_date):
    # 1. Obtiene slots reservados de PostgreSQL
    booked_slots = await get_booked_slots(start_date, end_date)
    
    # 2. Calcula rangos reservados (con buffer)
    booked_ranges = []
    for slot in booked_slots:
        appointment_start = slot['starts_at']
        appointment_end = appointment_start + timedelta(hours=2.0)
        
        # Aplica buffer: -1h antes, +1h después
        start_with_buffer = appointment_start - timedelta(hours=1.0)
        end_with_buffer = appointment_end + timedelta(hours=1.0)
        
        booked_ranges.append({
            'start': start_with_buffer,
            'end': end_with_buffer
        })
    
    # 3. Genera todos los posibles slots
    available_slots = []
    
    for date in date_range:
        for hour in [9, 12, 15, 18, 21]:  # operating_hours
            slot_datetime = datetime.combine(date, time(hour, 0))
            
            # 4. Verifica si hay overlap con reservas
            overlaps = False
            for booked_range in booked_ranges:
                if (slot_start_with_buffer < booked_range['end'] and 
                    slot_end_with_buffer > booked_range['start']):
                    overlaps = True
                    break
            
            # 5. Si no hay overlap, es disponible
            if not overlaps:
                available_slots.append(slot_datetime)
    
    return available_slots
```

---

### **Paso 8: Consulta a PostgreSQL**
📁 `app/db/queries.py` → `get_booked_slots()`

**Query SQL:**

```sql
SELECT 
    id,
    starts_at,
    service_name,
    customer_name,
    status
FROM booknetic_appointments
WHERE starts_at >= %s
  AND starts_at <= %s
  AND starts_at IS NOT NULL
  AND (status IS NULL OR status NOT IN ('cancelled', 'rejected'))
ORDER BY starts_at
```

**Tabla:** `booknetic_appointments` (Booknetic WordPress plugin)

---

### **Paso 9: Formato de Respuesta**
📁 `app/bot/availability.py` → Formatea respuesta final

**Estructura de respuesta:**

```
✅ ¡Tenemos disponibilidad!

📅 Sábado 14/02/2026: 10:00, 12:00, 15:00, 18:00, 21:00

👥 ¿Para cuántas personas sería?
Puedo ayudarte a reservar el horario perfecto.

💡 También puedes reservar directamente aquí:
https://hotboatchile.com/es/book-hotboat/
```

---

## 🔧 Componentes Clave

### **1. Detección Inteligente**
- ✅ Detecta palabras clave tradicionales
- ✅ Detecta fechas sin necesidad de decir "disponibilidad"
- ✅ Soporta múltiples formatos de fecha en español

### **2. Cálculo de Disponibilidad**
- ✅ Considera horarios de operación: `[9, 12, 15, 18, 21]`
- ✅ Duración del tour: `2.0 horas`
- ✅ Buffer time: `1.0 hora` antes y después
- ✅ Excluye reservas canceladas/rechazadas

### **3. Timezone**
- ✅ Usa `America/Santiago` (Chile)
- ✅ Todas las comparaciones en timezone correcto

### **4. Parsing de Fechas**
- ✅ "14 de febrero"
- ✅ "febrero 14"
- ✅ "14/02", "18-11"
- ✅ "jueves 6 de noviembre" (ignora día de semana)

---

## 📋 Ejemplos de Flujo Completo

### **Ejemplo 1: "¿Tienen disponibilidad mañana?"**

```
Usuario → WhatsApp → Webhook
  ↓
ConversationManager detecta "mañana" → is_availability_query() = True
  ↓
AvailabilityChecker.check_availability("mañana")
  ↓
Parsea: start_date = tomorrow 00:00, end_date = tomorrow 23:59
  ↓
get_available_slots() → Consulta PostgreSQL
  ↓
Calcula slots: [9, 12, 15, 18, 21] menos reservados
  ↓
Respuesta: "✅ Disponibilidad mañana: 9:00, 12:00, 15:00..."
  ↓
WhatsApp envía respuesta al usuario
```

### **Ejemplo 2: "14 de febrero"**

```
Usuario → WhatsApp → Webhook
  ↓
ConversationManager detecta fecha → _contains_date() = True
  ↓
AvailabilityChecker.check_availability("14 de febrero")
  ↓
_parse_spanish_date() → datetime(2026, 2, 14)
  ↓
start_date = 2026-02-14 00:00, end_date = 2026-02-14 23:59
  ↓
get_available_slots() → Solo slots del 14 de febrero
  ↓
Respuesta: "✅ Disponibilidad 14/02/2026: 9:00, 12:00..."
```

---

## 🗄️ Estructura de Base de Datos

### **Tabla: `booknetic_appointments`**
```sql
- id
- starts_at (TIMESTAMP)  ← Usado para calcular disponibilidad
- service_name
- customer_name
- status (NULL, 'cancelled', 'rejected')  ← Filtrado
```

### **Tabla: `whatsapp_conversations`**
```sql
- Guarda todas las conversaciones
- phone_number, message_text, response_text
- created_at, message_id
```

---

## 🎯 Configuración

### **Variables de Entorno (Railway)**
```env
DATABASE_URL=postgresql://...
WHATSAPP_API_TOKEN=...
WHATSAPP_PHONE_NUMBER_ID=...
WHATSAPP_VERIFY_TOKEN=...
```

### **Configuración de Disponibilidad**
📁 `app/availability/availability_config.py`

```python
operating_hours = [9, 12, 15, 18, 21]  # Horas disponibles
duration_hours = 2.0                    # Duración tour
buffer_hours = 1.0                      # Buffer time
```

---

## ✅ Validaciones Implementadas

1. ✅ **Buffer Time**: No ofrece slots muy cerca de reservas existentes
2. ✅ **Timezone**: Todo calculado en hora de Chile
3. ✅ **Parsing Flexible**: Múltiples formatos de fecha en español
4. ✅ **Exclusión de Estados**: Ignora reservas canceladas/rechazadas
5. ✅ **Overlap Detection**: Verifica conflictos correctamente

---

Este es el flujo completo de cómo funciona la consulta de disponibilidad en WhatsApp! 🚤⚓



