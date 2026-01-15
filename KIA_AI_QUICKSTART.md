# 🚀 Kia-Ai Quick Start

Get your WhatsApp management interface running in 5 minutes!

## Prerequisites

- ✅ WhatsApp bot already configured
- ✅ Python 3.9+ installed
- ✅ `.env` file configured with WhatsApp credentials

## Step 1: Start Kia-Ai Locally

**Windows:**
```bash
start_kia_ai.bat
```

**Linux/Mac:**
```bash
chmod +x start_kia_ai.sh
./start_kia_ai.sh
```

**Or manually:**
```bash
python -m app.main
```

## Step 2: Access the Interface

Open your browser:
```
http://localhost:8000
```

You should see the Kia-Ai interface! 🎉

## Step 3: Test It

1. ✅ View conversations in the sidebar
2. ✅ Click a conversation to view messages
3. ✅ Click "New Message" to send a custom WhatsApp message

## Step 4: Set Up Remote Access (Optional)

To access Kia-Ai from anywhere using Cloudflare Tunnel:

### Quick Setup (Linux/Mac)
```bash
chmod +x setup_cloudflare_tunnel.sh
./setup_cloudflare_tunnel.sh
```

### Manual Setup

1. **Install cloudflared:**

   **Windows:**
   ```powershell
   winget install --id Cloudflare.cloudflared
   ```

   **Linux:**
   ```bash
   wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
   sudo dpkg -i cloudflared-linux-amd64.deb
   ```

   **Mac:**
   ```bash
   brew install cloudflare/cloudflare/cloudflared
   ```

2. **Login to Cloudflare:**
   ```bash
   cloudflared tunnel login
   ```

3. **Create tunnel:**
   ```bash
   cloudflared tunnel create kia-ai
   ```

4. **Configure DNS:**
   ```bash
   cloudflared tunnel route dns kia-ai kia-ai.yourdomain.com
   ```

5. **Update config:**
   Edit `cloudflared-config.yml` with your tunnel ID and domain

6. **Run tunnel:**
   ```bash
   cloudflared tunnel --config cloudflared-config.yml run kia-ai
   ```

7. **Access remotely:**
   ```
   https://kia-ai.yourdomain.com
   ```

## Features

### 💬 View Conversations
- Real-time conversation list
- Search and filter
- Message history

### 📤 Send Messages
- Reply to existing conversations
- Send new messages to any number
- Format: `56912345678` (country code + number, no +)

### 👤 Manage Leads
- View customer information
- Track lead status
- See conversation history

### 🔄 Auto-Refresh
- Conversations update every 10 seconds
- Real-time message tracking

## API Endpoints

You can also use the API directly:

### Get all conversations
```bash
curl http://localhost:8000/api/conversations
```

### Get specific conversation
```bash
curl http://localhost:8000/api/conversations/56912345678
```

### Send message
```bash
curl -X POST http://localhost:8000/api/send-message \
  -H "Content-Type: application/json" \
  -d '{
    "to": "56912345678",
    "message": "Hello from Kia-Ai!"
  }'
```

## Troubleshooting

### Static files not loading?
```bash
# Check if files exist
ls app/static/

# Should show: index.html, styles.css, app.js
```

### Cannot send messages?
1. Check WhatsApp credentials in `.env`
2. Verify phone number format (no + sign)
3. Check logs for errors

### Cloudflare tunnel not working?
```bash
# Check tunnel status
cloudflared tunnel info kia-ai

# Verify DNS
nslookup kia-ai.yourdomain.com

# Check tunnel logs
cloudflared tunnel run kia-ai
```

## Next Steps

📖 Read the full documentation: [KIA_AI_SETUP.md](KIA_AI_SETUP.md)

🔐 Add authentication for production use

🚀 Deploy to production (Railway, Docker, etc.)

---

**Need help?** Check the troubleshooting section in the full documentation.

**Ready to go?** Start sending messages through Kia-Ai! 🎉

