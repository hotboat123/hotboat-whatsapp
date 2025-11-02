# 📊 Sistema de Leads y Importación de Conversaciones

## ✅ Funcionalidades Implementadas

### 1. **Gestión de Leads/Contactos**
- Clasificación automática de contactos
- Estados: `potential_client`, `bad_lead`, `customer`, `unknown`
- Notas y tags para cada lead
- Historial de interacciones

### 2. **Historial de Conversaciones**
- Las conversaciones se cargan automáticamente desde la base de datos
- El bot mantiene contexto de conversaciones previas
- Soporte para importar conversaciones existentes

### 3. **Sistema de Importación**
- Importar desde archivos JSON
- Importar desde archivos CSV
- Mantener historial completo de conversaciones

## 📋 Estructura de Base de Datos

### Tabla: `whatsapp_leads`
```sql
- id: SERIAL PRIMARY KEY
- phone_number: VARCHAR(20) UNIQUE
- customer_name: VARCHAR(100)
- lead_status: VARCHAR(20) -- 'potential_client', 'bad_lead', 'customer', 'unknown'
- notes: TEXT
- tags: TEXT[]
- created_at: TIMESTAMP
- updated_at: TIMESTAMP
- last_interaction_at: TIMESTAMP
```

### Tabla: `whatsapp_conversations` (actualizada)
```sql
- id: SERIAL PRIMARY KEY
- phone_number: VARCHAR(20)
- customer_name: VARCHAR(100)
- message_text: TEXT
- response_text: TEXT
- message_type: VARCHAR(20)
- message_id: VARCHAR(100) -- Para evitar duplicados
- direction: VARCHAR(10) -- 'incoming' o 'outgoing'
- created_at: TIMESTAMP
- imported: BOOLEAN -- True si fue importado
```

## 🚀 Cómo Usar

### 1. Crear las tablas en PostgreSQL

Ejecuta los scripts SQL:
```bash
# Conectarse a PostgreSQL y ejecutar:
psql -h turntable.proxy.rlwy.net -p 48129 -U postgres -d railway -f create_leads_table.sql
```

O manualmente en tu cliente SQL:
```sql
-- Ver create_leads_table.sql para el SQL completo
```

### 2. Importar Conversaciones Existentes

#### Opción A: Desde JSON

Crea un archivo `conversations.json`:
```json
[
  {
    "phone_number": "56912345678",
    "customer_name": "Juan Pérez",
    "conversations": [
      {
        "message": "Hola, quiero información",
        "response": "Hola! Te puedo ayudar...",
        "timestamp": "2025-01-15T10:00:00Z",
        "direction": "incoming",
        "message_id": "msg_123"
      }
    ]
  }
]
```

Importar:
```bash
python import_whatsapp_conversations.py conversations.json
```

#### Opción B: Desde CSV

Crea un archivo `conversations.csv`:
```csv
phone_number,customer_name,message,response,timestamp,direction,message_id
56912345678,Juan Pérez,Hola,Respuesta,2025-01-15 10:00:00,incoming,msg_123
```

Importar:
```bash
python import_whatsapp_conversations.py conversations.csv csv
```

#### Opción C: Template

Crear template de ejemplo:
```bash
python import_whatsapp_conversations.py template
```

### 3. Clasificar Leads

Usa el endpoint API:

```bash
# Clasificar como potencial cliente
curl -X PUT http://localhost:8000/leads/56912345678/status \
  -H "Content-Type: application/json" \
  -d '{
    "lead_status": "potential_client",
    "notes": "Muy interesado, pregunta por precios frecuentemente"
  }'

# Clasificar como mal lead
curl -X PUT http://localhost:8000/leads/56912345678/status \
  -H "Content-Type: application/json" \
  -d '{
    "lead_status": "bad_lead",
    "notes": "Solo spam, no muestra interés real"
  }'
```

### 4. Ver Leads Clasificados

```bash
# Ver todos los leads
curl http://localhost:8000/leads

# Ver solo potenciales clientes
curl http://localhost:8000/leads?lead_status=potential_client

# Ver malos leads
curl http://localhost:8000/leads?lead_status=bad_lead
```

## 📊 Endpoints API

### Leads Management

- `GET /leads` - Listar todos los leads
  - Query params: `lead_status` (opcional), `limit` (default: 50)
  
- `GET /leads/{phone_number}` - Obtener información de un lead y su historial

- `PUT /leads/{phone_number}/status` - Clasificar un lead
  ```json
  {
    "lead_status": "potential_client" | "bad_lead" | "customer" | "unknown",
    "notes": "Notas opcionales"
  }
  ```

### Importación

- `POST /import/conversations` - Importar conversaciones
  ```json
  {
    "phone_number": "56912345678",
    "customer_name": "Juan Pérez",
    "conversations": [
      {
        "message": "texto mensaje",
        "response": "texto respuesta",
        "timestamp": "2025-01-15T10:00:00Z",
        "direction": "incoming",
        "message_id": "optional_id"
      }
    ]
  }
  ```

## 🔄 Cómo Funciona el Historial

1. **Cuando un usuario envía un mensaje:**
   - El bot busca en la base de datos si hay historial previo
   - Carga las últimas 50 conversaciones
   - Usa ese contexto para generar respuestas más contextuales

2. **Nuevas conversaciones:**
   - Se guardan automáticamente en `whatsapp_conversations`
   - Se actualiza `last_interaction_at` en `whatsapp_leads`

3. **Importación:**
   - Las conversaciones importadas se marcan con `imported = TRUE`
   - Se evitan duplicados usando `message_id` si está disponible

## 📝 Estados de Lead

- **`unknown`** (por defecto) - Aún no clasificado
- **`potential_client`** - Cliente potencial, muestra interés
- **`bad_lead`** - No es un buen lead (spam, no interesado, etc.)
- **`customer`** - Ya es cliente confirmado

## 💡 Tips para Clasificación

### Potential Client (Cliente Potencial):
- Pregunta por precios específicos
- Menciona fechas de interés
- Hace preguntas detalladas sobre el servicio
- Muestra intención de reservar

### Bad Lead:
- Solo envía spam
- No responde a preguntas
- Solo busca información sin mostrar interés real
- Mensajes inapropiados

## 🔧 Exportar desde WhatsApp Business

Para exportar tus conversaciones actuales de WhatsApp Business:

1. **WhatsApp Business Manager:**
   - Ve a Configuración → Conversaciones
   - Exporta las conversaciones en formato CSV o JSON

2. **WhatsApp Desktop:**
   - Abre la conversación
   - Exporta el chat (si la opción está disponible)

3. **Manual:**
   - Crea el archivo JSON/CSV con el formato del template
   - Importa usando el script

## ✅ Próximos Pasos

Una vez implementado:
1. Ejecuta `create_leads_table.sql` en tu base de datos
2. Exporta tus conversaciones de WhatsApp Business
3. Convierte al formato JSON/CSV según el template
4. Importa usando el script
5. Clasifica los leads usando la API o manualmente

---

**El sistema ahora puede:**
- ✅ Retener historial completo de conversaciones
- ✅ Cargar contexto automáticamente cuando alguien escribe
- ✅ Clasificar leads como potencial cliente o mal lead
- ✅ Importar conversaciones existentes de WhatsApp Business

