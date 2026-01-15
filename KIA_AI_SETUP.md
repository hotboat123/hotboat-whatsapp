# 🤖 Kia-Ai Setup Guide

Complete guide to set up the Kia-Ai WhatsApp Management Interface with Cloudflare Tunnel for remote access.

## Table of Contents
- [Overview](#overview)
- [Features](#features)
- [Prerequisites](#prerequisites)
- [Installation Steps](#installation-steps)
- [Cloudflare Tunnel Setup](#cloudflare-tunnel-setup)
- [Usage](#usage)
- [Troubleshooting](#troubleshooting)

---

## Overview

**Kia-Ai** is a beautiful, modern web interface that allows you to:
- 📱 View all WhatsApp conversations in real-time
- 💬 Send custom messages to customers through your WhatsApp bot
- 👤 Manage lead information
- 🔍 Search and filter conversations
- 📊 Track message history

The interface uses **Cloudflare Tunnel** to provide secure remote access without exposing ports or configuring firewalls.

---

## Features

✅ **Real-time Conversations** - View and manage all WhatsApp chats
✅ **Send Custom Messages** - Send messages to any customer
✅ **Lead Management** - View customer information and status
✅ **Dark Modern UI** - Beautiful WhatsApp-inspired interface
✅ **Secure Remote Access** - via Cloudflare Tunnel
✅ **No Port Forwarding Needed** - Works from anywhere
✅ **Auto-refresh** - Conversations update every 10 seconds

---

## Prerequisites

Before starting, make sure you have:

1. **Python 3.9+** installed
2. **The WhatsApp Bot** already configured and running
3. **Cloudflare Account** (free tier works)
4. **A domain** (optional, but recommended)

---

## Installation Steps

### 1. Install Dependencies

The required dependencies are already in `requirements.txt`:

```bash
pip install -r requirements.txt
```

### 2. Verify Static Files

The Kia-Ai interface files should be in `app/static/`:
- `app/static/index.html`
- `app/static/styles.css`
- `app/static/app.js`

### 3. Start the Application

```bash
python -m app.main
```

Or using uvicorn:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 4. Test Locally

Open your browser and go to:
```
http://localhost:8000
```

You should see the Kia-Ai interface! 🎉

---

## Cloudflare Tunnel Setup

Cloudflare Tunnel allows you to securely expose your local application to the internet without opening ports or dealing with firewalls.

### Step 1: Install Cloudflared

**Windows:**
```powershell
# Download from: https://github.com/cloudflare/cloudflared/releases
# Or use winget:
winget install --id Cloudflare.cloudflared
```

**Linux:**
```bash
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i cloudflared-linux-amd64.deb
```

**macOS:**
```bash
brew install cloudflare/cloudflare/cloudflared
```

### Step 2: Login to Cloudflare

```bash
cloudflared tunnel login
```

This will:
1. Open your browser
2. Ask you to select a domain
3. Download a certificate to `~/.cloudflared/cert.pem`

### Step 3: Create a Tunnel

```bash
cloudflared tunnel create kia-ai
```

This will:
1. Create a tunnel named "kia-ai"
2. Generate a tunnel ID (save this!)
3. Create a credentials file at `~/.cloudflared/TUNNEL_ID.json`

**Example output:**
```
Tunnel credentials written to /root/.cloudflared/12345678-1234-1234-1234-123456789abc.json
Created tunnel kia-ai with id 12345678-1234-1234-1234-123456789abc
```

### Step 4: Configure the Tunnel

Edit `cloudflared-config.yml` in your project root:

```yaml
tunnel: YOUR_TUNNEL_ID  # Replace with your actual tunnel ID
credentials-file: /root/.cloudflared/YOUR_TUNNEL_ID.json

ingress:
  - hostname: kia-ai.yourdomain.com  # Replace with your domain
    service: http://localhost:8000
  - service: http_status:404

metrics: 0.0.0.0:2000
```

### Step 5: Create DNS Record

```bash
cloudflared tunnel route dns kia-ai kia-ai.yourdomain.com
```

Replace `kia-ai.yourdomain.com` with your desired subdomain.

### Step 6: Run the Tunnel

**Option A: Run manually**
```bash
cloudflared tunnel --config cloudflared-config.yml run kia-ai
```

**Option B: Install as a service (recommended)**

**Windows:**
```powershell
cloudflared service install
```

**Linux:**
```bash
sudo cloudflared service install
sudo systemctl start cloudflared
sudo systemctl enable cloudflared
```

### Step 7: Access Your Interface

Now you can access Kia-Ai from anywhere:
```
https://kia-ai.yourdomain.com
```

---

## Usage

### Viewing Conversations

1. **Open Kia-Ai** in your browser
2. **Conversations** appear on the left sidebar
3. **Click any conversation** to view the full message history
4. **Lead information** appears on the right panel

### Sending Messages

**Option 1: Reply to existing conversation**
1. Select a conversation
2. Type your message in the input box at the bottom
3. Click "Send 📤"

**Option 2: Send new message**
1. Click "➕ New Message" button
2. Enter phone number (format: `56912345678` - with country code, no +)
3. Type your message
4. Click "Send Message 📤"

### Searching Conversations

Use the search box at the top of the conversations list to filter by:
- Customer name
- Phone number
- Message content

---

## API Endpoints

Kia-Ai uses these API endpoints (you can use them directly too):

### Get Conversations
```http
GET /api/conversations?limit=50
```

### Get Specific Conversation
```http
GET /api/conversations/{phone_number}
```

### Send Message
```http
POST /api/send-message
Content-Type: application/json

{
  "to": "56912345678",
  "message": "Your custom message here"
}
```

---

## Running in Production

### Option 1: Railway (Recommended)

Your app is already configured for Railway. Just push your changes:

```bash
git add .
git commit -m "Add Kia-Ai interface"
git push
```

Then set up the Cloudflare Tunnel on your Railway service:

1. Add `cloudflared` to your Railway service
2. Set the config as environment variables
3. Or use a separate container for the tunnel

### Option 2: Docker

Create a `Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Build and run:
```bash
docker build -t kia-ai .
docker run -p 8000:8000 --env-file .env kia-ai
```

### Option 3: Systemd Service (Linux)

Create `/etc/systemd/system/kia-ai.service`:

```ini
[Unit]
Description=Kia-Ai WhatsApp Management Interface
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/hotboat-whatsapp
Environment="PATH=/path/to/venv/bin"
ExecStart=/path/to/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable kia-ai
sudo systemctl start kia-ai
```

---

## Security Recommendations

1. **Enable Authentication** (add to your FastAPI app):
   ```python
   from fastapi.security import HTTPBasic, HTTPBasicCredentials
   security = HTTPBasic()
   ```

2. **Use HTTPS** - Cloudflare Tunnel provides this automatically

3. **Restrict Access** - Use Cloudflare Access to add authentication:
   ```bash
   # In your Cloudflare dashboard:
   Zero Trust > Access > Applications > Add an application
   ```

4. **Monitor Access** - Check Cloudflare Tunnel logs:
   ```bash
   cloudflared tunnel info kia-ai
   ```

---

## Troubleshooting

### Static Files Not Loading

**Problem:** CSS/JS not loading, interface looks broken

**Solution:**
```bash
# Check if static directory exists
ls -la app/static/

# Verify FastAPI is mounting static files
# Check logs for: "StaticFiles(directory='app/static')"
```

### Cannot Send Messages

**Problem:** "Failed to send message" error

**Solutions:**
1. Check WhatsApp API credentials in `.env`:
   ```
   WHATSAPP_API_TOKEN=your_token
   WHATSAPP_PHONE_NUMBER_ID=your_phone_id
   ```

2. Verify phone number format (no + sign, include country code)

3. Check API logs:
   ```bash
   tail -f logs/app.log
   ```

### Cloudflare Tunnel Not Working

**Problem:** Cannot access via custom domain

**Solutions:**

1. **Check tunnel status:**
   ```bash
   cloudflared tunnel info kia-ai
   ```

2. **Verify DNS:**
   ```bash
   nslookup kia-ai.yourdomain.com
   ```

3. **Check tunnel logs:**
   ```bash
   cloudflared tunnel run kia-ai
   ```

4. **Verify config file:**
   ```bash
   cloudflared tunnel ingress validate
   ```

### Conversations Not Loading

**Problem:** Empty conversation list

**Solutions:**

1. **Check database connection:**
   ```python
   # Test database
   python -c "from app.db.connection import get_connection; print('DB OK')"
   ```

2. **Verify conversations table exists:**
   ```sql
   SELECT COUNT(*) FROM conversations;
   ```

3. **Check API endpoint directly:**
   ```bash
   curl http://localhost:8000/api/conversations
   ```

---

## Advanced Configuration

### Custom Branding

Edit `app/static/index.html` to change:
- Logo and title
- Colors in `app/static/styles.css` (CSS variables at the top)

### Add Authentication

Add basic auth to `app/main.py`:

```python
from fastapi import Depends
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import secrets

security = HTTPBasic()

def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = secrets.compare_digest(credentials.username, "admin")
    correct_password = secrets.compare_digest(credentials.password, "your_password")
    if not (correct_username and correct_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return credentials.username

@app.get("/", dependencies=[Depends(verify_credentials)])
async def root():
    # ... rest of code
```

### Multiple Tunnels

You can create multiple tunnels for different environments:

```bash
cloudflared tunnel create kia-ai-dev
cloudflared tunnel create kia-ai-prod
```

---

## Support

If you encounter issues:

1. **Check logs:**
   ```bash
   # Application logs
   tail -f logs/app.log
   
   # Cloudflare Tunnel logs
   journalctl -u cloudflared -f
   ```

2. **Test API endpoints directly:**
   ```bash
   curl http://localhost:8000/health
   curl http://localhost:8000/api/conversations
   ```

3. **Verify environment variables:**
   ```bash
   python -c "from app.config import get_settings; print(get_settings())"
   ```

---

## Next Steps

- 🔐 Add authentication to Kia-Ai
- 📊 Add analytics dashboard
- 🤖 Implement AI-powered response suggestions
- 📱 Create mobile app version
- 🔔 Add push notifications
- 📁 Add file/image sending capability

---

## Credits

**Kia-Ai** - WhatsApp Management Interface
Built with ❤️ for Hot Boat Chile

Technologies:
- FastAPI
- Vanilla JavaScript
- Cloudflare Tunnel
- WhatsApp Business API

---

## License

This project is part of the Hot Boat WhatsApp Bot system.

---

**Questions?** Check the troubleshooting section or review the API documentation.

**Ready to start?** Follow the installation steps above and you'll be up and running in minutes! 🚀

