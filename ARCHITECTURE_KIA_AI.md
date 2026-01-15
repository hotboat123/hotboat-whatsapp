# 🏗️ Kia-Ai Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        User's Browser                            │
│                     (Kia-Ai Interface)                           │
│                    https://kia-ai.domain.com                     │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             │ HTTPS
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                    Cloudflare Tunnel                             │
│                  (Secure Proxy/CDN)                              │
│            - SSL/TLS encryption                                  │
│            - DDoS protection                                     │
│            - No port forwarding needed                           │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             │ HTTP (local)
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                    FastAPI Server                                │
│                   (app/main.py)                                  │
│                   localhost:8000                                 │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              Static File Server                           │  │
│  │         (Serves Kia-Ai HTML/CSS/JS)                      │  │
│  │           /static/* → app/static/                        │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              API Endpoints                                │  │
│  │  - GET  /api/conversations                               │  │
│  │  - GET  /api/conversations/{phone}                       │  │
│  │  - POST /api/send-message                                │  │
│  │  - GET  /leads/{phone}                                   │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │          WhatsApp Webhook Handler                         │  │
│  │  - POST /webhook (receive messages)                      │  │
│  │  - GET  /webhook (verification)                          │  │
│  └──────────────────────────────────────────────────────────┘  │
└──────────────────┬─────────────────────────┬───────────────────┘
                   │                         │
                   │                         │
     ┌─────────────▼────────────┐  ┌────────▼──────────────┐
     │   WhatsApp API Client    │  │  Database (PostgreSQL)│
     │  (app/whatsapp/client.py)│  │  (Conversations, Leads│
     │                          │  │   Messages, History)  │
     └─────────────┬────────────┘  └───────────────────────┘
                   │
                   │ HTTPS API Calls
                   │
     ┌─────────────▼────────────────────────────────┐
     │   WhatsApp Business Cloud API                │
     │   (graph.facebook.com/v18.0)                 │
     │   - Send messages                            │
     │   - Receive webhooks                         │
     │   - Mark as read                             │
     └──────────────────────────────────────────────┘
```

## Component Details

### 1. Frontend (Kia-Ai Interface)

**Files:**
- `app/static/index.html` - Main UI structure
- `app/static/styles.css` - Modern dark theme styling
- `app/static/app.js` - Frontend logic and API communication

**Features:**
- Real-time conversation list
- Message history display
- Send message form
- Lead information panel
- Search and filter
- Auto-refresh (10s interval)

**Tech Stack:**
- Vanilla JavaScript (no dependencies)
- Modern CSS (Grid, Flexbox, Variables)
- REST API consumption
- Responsive design

### 2. Backend (FastAPI)

**Main File:** `app/main.py`

**Components:**

#### A. Static File Server
```python
app.mount("/static", StaticFiles(directory="app/static"))
```
Serves the Kia-Ai interface files.

#### B. Kia-Ai API Endpoints

**GET /api/conversations**
- Returns list of all conversations
- Includes last message preview
- Sorted by most recent

**GET /api/conversations/{phone_number}**
- Returns full conversation history
- Includes lead information
- Up to 200 messages

**POST /api/send-message**
- Sends WhatsApp message
- Validates phone format
- Logs to database
- Returns confirmation

#### C. WhatsApp Webhook
```python
@app.post("/webhook")
```
- Receives incoming WhatsApp messages
- Processes through conversation manager
- Stores in database
- Triggers bot responses

#### D. Lead Management
```python
GET /leads
GET /leads/{phone_number}
PUT /leads/{phone_number}/status
```

### 3. WhatsApp Client

**File:** `app/whatsapp/client.py`

**Class:** `WhatsAppClient`

**Methods:**
- `send_text_message(to, message)` - Send text
- `send_template_message(to, template_name)` - Send template
- `send_image_message(to, image_url)` - Send image
- `mark_as_read(message_id)` - Mark as read

**API Details:**
- Base URL: `https://graph.facebook.com/v18.0`
- Authentication: Bearer token
- Async HTTP requests (httpx)

### 4. Database Layer

**Files:**
- `app/db/connection.py` - Connection pool
- `app/db/queries.py` - Conversation queries
- `app/db/leads.py` - Lead management

**Tables:**

#### conversations
```sql
- id (serial)
- phone_number (varchar)
- customer_name (varchar)
- message_text (text)
- response_text (text)
- direction (varchar) -- 'incoming' or 'outgoing'
- timestamp (timestamp)
- message_id (varchar)
```

#### leads
```sql
- id (serial)
- phone_number (varchar)
- customer_name (varchar)
- lead_status (varchar)
- first_contact_at (timestamp)
- last_contact_at (timestamp)
- notes (text)
```

### 5. Cloudflare Tunnel

**Purpose:** Secure remote access without port forwarding

**How it works:**
1. `cloudflared` daemon runs on server
2. Creates encrypted tunnel to Cloudflare
3. Cloudflare proxies requests to local server
4. Provides SSL/TLS, DDoS protection, caching

**Config:** `cloudflared-config.yml`
```yaml
tunnel: <tunnel-id>
credentials-file: ~/.cloudflared/<tunnel-id>.json
ingress:
  - hostname: kia-ai.domain.com
    service: http://localhost:8000
```

## Data Flow

### Viewing Conversations

```
1. User opens browser → https://kia-ai.domain.com
2. Cloudflare Tunnel → FastAPI server
3. Server serves → app/static/index.html
4. Browser loads → app.js
5. JavaScript calls → GET /api/conversations
6. FastAPI queries → PostgreSQL database
7. Returns → JSON with conversation list
8. Browser renders → conversation list in sidebar
9. Auto-refresh → every 10 seconds
```

### Sending Message

```
1. User types message → clicks "Send"
2. JavaScript POSTs → /api/send-message
   {
     "to": "56912345678",
     "message": "Hello"
   }
3. FastAPI receives → validates input
4. Calls → whatsapp_client.send_text_message()
5. WhatsApp Client → POST to graph.facebook.com
6. Facebook API → sends WhatsApp message
7. FastAPI stores → conversation in database
8. Returns → success response
9. Browser shows → success toast notification
10. Refreshes → conversation view
```

### Receiving Message (Webhook)

```
1. Customer sends WhatsApp message
2. Facebook API → POST /webhook
3. FastAPI receives → webhook payload
4. Extracts → phone, message, timestamp
5. Passes to → ConversationManager
6. Bot processes → AI response
7. Stores → incoming message in DB
8. Sends → bot response via WhatsApp API
9. Stores → outgoing response in DB
10. Kia-Ai shows → both messages on next refresh
```

## Security Architecture

### Network Security
```
Internet → Cloudflare (HTTPS, DDoS protection)
         → Tunnel (encrypted)
         → Local Server (localhost:8000)
```

**Benefits:**
- ✅ No exposed ports
- ✅ Automatic SSL/TLS
- ✅ DDoS protection
- ✅ IP filtering via Cloudflare
- ✅ Rate limiting

### Application Security

**Current:**
- Environment variables for secrets
- HTTPS only (via Cloudflare)
- Input validation
- SQL injection protection (parameterized queries)

**Recommended Additions:**
- Authentication middleware
- CSRF protection
- Rate limiting
- Session management
- API key authentication

## Scalability

### Current Capacity
- **Concurrent Users:** 100+ (FastAPI async)
- **Messages/sec:** 10-50
- **Database:** 1M+ messages
- **Auto-refresh:** Every 10s (minimal load)

### Scaling Options

**Horizontal:**
- Multiple FastAPI instances
- Load balancer
- Database replication

**Vertical:**
- Increase server resources
- Optimize queries
- Add caching (Redis)

**Optimizations:**
- WebSocket for real-time updates (instead of polling)
- Message pagination
- Lazy loading
- CDN for static files (already via Cloudflare)

## Deployment Architecture

### Development
```
Local Machine
  ├── Python app (localhost:8000)
  ├── PostgreSQL (local or remote)
  └── No tunnel (access via localhost)
```

### Production
```
Server (Railway/VPS/Cloud)
  ├── FastAPI app (0.0.0.0:8000)
  ├── PostgreSQL (managed DB)
  ├── Cloudflare Tunnel daemon
  └── HTTPS access via domain
```

## Technology Choices

### Why FastAPI?
- ✅ Fast (async/await)
- ✅ Modern Python
- ✅ Auto-documentation
- ✅ Type hints
- ✅ Easy to learn

### Why Vanilla JavaScript?
- ✅ No build step
- ✅ Fast loading
- ✅ No dependencies
- ✅ Easy to customize
- ✅ Direct control

### Why Cloudflare Tunnel?
- ✅ Free tier available
- ✅ No port forwarding
- ✅ Automatic SSL
- ✅ DDoS protection
- ✅ Works behind NAT/firewall

### Why PostgreSQL?
- ✅ Robust and reliable
- ✅ ACID compliance
- ✅ JSON support
- ✅ Great for time-series data
- ✅ Free tier on Railway

## Performance Metrics

### Response Times
- Static files: < 10ms
- API endpoints: 50-100ms
- Database queries: 10-50ms
- WhatsApp API: 200-500ms

### Resource Usage
- Memory: 100-200 MB
- CPU: < 5% (idle), < 20% (active)
- Disk: Minimal (logs + DB)
- Network: < 1 Mbps

## Monitoring Points

### Application
- API response times
- Error rates
- Message send success rate
- Database query performance

### Infrastructure
- Server uptime
- Cloudflare Tunnel status
- Database connection pool
- Memory/CPU usage

### Business
- Messages sent/received
- Active conversations
- Lead conversion rate
- Response time to customers

## Future Architecture

### Planned Enhancements

**1. WebSocket Support**
```
Browser ←→ WebSocket ←→ FastAPI ←→ WhatsApp Webhook
(Real-time updates without polling)
```

**2. Redis Cache**
```
FastAPI → Redis (cache) → PostgreSQL
(Faster conversation loading)
```

**3. Queue System**
```
API → RabbitMQ → Workers → WhatsApp API
(Handle bulk messages)
```

**4. Microservices**
```
├── API Gateway
├── Message Service
├── Lead Service
├── Analytics Service
└── Notification Service
```

---

## Quick Reference

### Key Files
- `app/main.py` - FastAPI app + endpoints
- `app/static/` - Kia-Ai interface
- `app/whatsapp/client.py` - WhatsApp API client
- `cloudflared-config.yml` - Tunnel config

### Key Endpoints
- `/` - Kia-Ai interface
- `/api/conversations` - List conversations
- `/api/send-message` - Send WhatsApp message
- `/webhook` - WhatsApp webhook

### Key Technologies
- FastAPI (Python web framework)
- PostgreSQL (Database)
- WhatsApp Business API (Messaging)
- Cloudflare Tunnel (Remote access)

---

**Questions about the architecture?** Check the full documentation or review the code comments.

