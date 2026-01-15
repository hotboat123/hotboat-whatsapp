# 🤖 Kia-Ai - WhatsApp Management Interface

![Status](https://img.shields.io/badge/status-ready-brightgreen)
![Platform](https://img.shields.io/badge/platform-web-blue)
![Python](https://img.shields.io/badge/python-3.9+-blue)

A beautiful, modern web interface for managing WhatsApp conversations and sending custom messages to customers through your WhatsApp bot.

## 🎯 What is Kia-Ai?

Kia-Ai is a comprehensive chat management interface that connects to your WhatsApp Business API bot, allowing you to:

- 📱 **View all conversations** in a beautiful, WhatsApp-like interface
- 💬 **Send custom messages** to any customer
- 🔍 **Search and filter** conversations
- 👤 **Manage lead information** and track customer status
- 🌐 **Access remotely** via Cloudflare Tunnel
- 🔄 **Real-time updates** with automatic refresh

## 🖼️ Features

### Modern Interface
- Dark theme inspired by WhatsApp Web
- Responsive design (works on mobile, tablet, desktop)
- Real-time message updates every 10 seconds
- Smooth animations and transitions

### Conversation Management
- View all WhatsApp conversations in one place
- Search by customer name or phone number
- See message history with timestamps
- Filter conversations instantly

### Message Sending
- Reply to existing conversations
- Send new messages to any phone number
- Character counter (4096 char limit)
- Toast notifications for confirmations

### Lead Tracking
- View customer information in right panel
- Track lead status (Potential Client, Customer, Bad Lead, Unknown)
- See first and last contact dates
- View conversation statistics

## 🚀 Quick Start

### 1. Start the Application

**Windows:**
```bash
start_kia_ai.bat
```

**Linux/Mac:**
```bash
chmod +x start_kia_ai.sh
./start_kia_ai.sh
```

**Manual:**
```bash
python -m app.main
```

### 2. Open in Browser

```
http://localhost:8000
```

### 3. Start Using

- View conversations on the left
- Click any conversation to see messages
- Type and send replies
- Click "New Message" to message anyone

## 🌐 Remote Access Setup

Access Kia-Ai from anywhere using Cloudflare Tunnel (free, secure, no port forwarding needed).

### Automated Setup

```bash
chmod +x setup_cloudflare_tunnel.sh
./setup_cloudflare_tunnel.sh
```

### Manual Setup

See [KIA_AI_SETUP.md](KIA_AI_SETUP.md) for detailed instructions.

## 📁 Project Structure

```
hotboat-whatsapp/
├── app/
│   ├── static/              # Kia-Ai interface files
│   │   ├── index.html       # Main interface
│   │   ├── styles.css       # Styling
│   │   └── app.js           # Frontend logic
│   ├── main.py              # FastAPI app (includes Kia-Ai endpoints)
│   ├── whatsapp/
│   │   └── client.py        # WhatsApp API client
│   └── ...
├── cloudflared-config.yml   # Cloudflare Tunnel config
├── start_kia_ai.bat         # Windows start script
├── start_kia_ai.sh          # Linux/Mac start script
├── setup_cloudflare_tunnel.sh  # Auto tunnel setup
├── KIA_AI_SETUP.md          # Full documentation
├── KIA_AI_QUICKSTART.md     # Quick start guide
└── README_KIA_AI.md         # This file
```

## 🔌 API Endpoints

Kia-Ai provides REST API endpoints you can use directly:

### Get Conversations
```http
GET /api/conversations?limit=50
```

Returns list of all conversations with latest messages.

### Get Specific Conversation
```http
GET /api/conversations/{phone_number}
```

Returns full conversation history and lead info for a phone number.

### Send Message
```http
POST /api/send-message
Content-Type: application/json

{
  "to": "56912345678",
  "message": "Your message here"
}
```

Sends a WhatsApp message. Phone format: country code + number, no +

### Get Leads
```http
GET /leads?lead_status=potential_client&limit=50
```

Get leads filtered by status.

## 💻 Technology Stack

- **Backend:** FastAPI (Python)
- **Frontend:** Vanilla JavaScript (no frameworks)
- **Styling:** Custom CSS with modern design
- **API:** WhatsApp Business Cloud API
- **Database:** PostgreSQL
- **Tunnel:** Cloudflare Tunnel
- **Deployment:** Railway / Docker / Systemd

## 🔧 Configuration

### Environment Variables

Kia-Ai uses the same `.env` file as your WhatsApp bot:

```env
# WhatsApp API
WHATSAPP_API_TOKEN=your_token
WHATSAPP_PHONE_NUMBER_ID=your_phone_id
WHATSAPP_BUSINESS_ACCOUNT_ID=your_account_id
WHATSAPP_VERIFY_TOKEN=your_verify_token

# Database
DATABASE_URL=postgresql://...

# AI
GROQ_API_KEY=your_groq_key

# Server
PORT=8000
HOST=0.0.0.0
```

No additional configuration needed!

## 🔒 Security

### Current Status
- ✅ HTTPS via Cloudflare Tunnel
- ✅ Secure WebSocket connections
- ⚠️ No authentication (add for production)

### Recommendations for Production

1. **Add Authentication:**
   ```python
   from fastapi.security import HTTPBasic
   # Add to endpoints
   ```

2. **Use Cloudflare Access:**
   - Add authentication layer in Cloudflare dashboard
   - Zero Trust > Access > Applications

3. **Restrict IP Access:**
   - Configure firewall rules
   - Use Cloudflare WAF

4. **Monitor Access:**
   - Check logs regularly
   - Set up alerts

## 📊 Usage Examples

### View Today's Conversations

```javascript
fetch('/api/conversations?limit=100')
  .then(r => r.json())
  .then(data => console.log(data.conversations));
```

### Send Bulk Messages

```javascript
const customers = ['56912345678', '56987654321'];
const message = 'Special offer today!';

for (const phone of customers) {
  await fetch('/api/send-message', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ to: phone, message })
  });
}
```

### Search Conversations

```javascript
// Search in frontend
const searchTerm = 'booking';
const conversations = document.querySelectorAll('.conversation-item');
conversations.forEach(conv => {
  conv.style.display = conv.textContent.toLowerCase().includes(searchTerm) 
    ? 'block' 
    : 'none';
});
```

## 🐛 Troubleshooting

### Interface Not Loading

**Problem:** Blank page or 404

**Solution:**
```bash
# Check static files exist
ls app/static/
# Should show: index.html, styles.css, app.js

# Restart server
python -m app.main
```

### Cannot Send Messages

**Problem:** "Failed to send message" error

**Solution:**
1. Check WhatsApp credentials in `.env`
2. Verify phone format: `56912345678` (no + sign)
3. Check API token is valid
4. Review logs: `tail -f logs/app.log`

### Conversations Empty

**Problem:** No conversations showing

**Solution:**
1. Check database connection
2. Verify conversations table has data
3. Test endpoint: `curl http://localhost:8000/api/conversations`

### Cloudflare Tunnel Issues

**Problem:** Cannot access via domain

**Solution:**
```bash
# Check tunnel status
cloudflared tunnel info kia-ai

# Verify DNS
nslookup kia-ai.yourdomain.com

# Check config
cloudflared tunnel ingress validate

# View logs
cloudflared tunnel run kia-ai
```

See [KIA_AI_SETUP.md](KIA_AI_SETUP.md) for more troubleshooting.

## 📈 Performance

- **Response Time:** < 100ms for API calls
- **Auto-refresh:** Every 10 seconds
- **Message Limit:** 4096 characters (WhatsApp limit)
- **Conversations:** Loads 50 by default (configurable)
- **Message History:** 200 messages per conversation

## 🚀 Deployment Options

### Option 1: Railway (Recommended)
Already configured! Just push:
```bash
git add .
git commit -m "Add Kia-Ai interface"
git push
```

### Option 2: Docker
```bash
docker build -t kia-ai .
docker run -p 8000:8000 --env-file .env kia-ai
```

### Option 3: Linux Service
```bash
sudo systemctl enable kia-ai
sudo systemctl start kia-ai
```

See [KIA_AI_SETUP.md](KIA_AI_SETUP.md) for detailed deployment instructions.

## 🎨 Customization

### Change Colors

Edit `app/static/styles.css`:

```css
:root {
    --primary-color: #25D366;  /* Main green */
    --secondary-color: #128C7E; /* Dark green */
    --bg-dark: #0b141a;        /* Background */
    /* ... customize other colors */
}
```

### Change Branding

Edit `app/static/index.html`:

```html
<h1>🤖 Your Brand Name</h1>
<p class="subtitle">Your Subtitle</p>
```

### Add Features

The codebase is modular and easy to extend:
- Add new API endpoints in `app/main.py`
- Add UI features in `app/static/app.js`
- Style changes in `app/static/styles.css`

## 📚 Documentation

- 📖 [Quick Start Guide](KIA_AI_QUICKSTART.md) - Get running in 5 minutes
- 📖 [Full Setup Guide](KIA_AI_SETUP.md) - Complete documentation
- 📖 [Cloudflare Config](cloudflared-config.yml) - Tunnel configuration

## 🤝 Support

### Getting Help

1. **Check documentation** - Most issues are covered
2. **Review logs** - Check application and tunnel logs
3. **Test API directly** - Use curl to test endpoints
4. **Verify credentials** - Ensure WhatsApp API is working

### Common Issues

| Issue | Solution |
|-------|----------|
| Static files 404 | Check `app/static/` exists |
| Cannot send messages | Verify WhatsApp credentials |
| Empty conversations | Check database connection |
| Tunnel not working | Verify cloudflared config |

## 🎯 Use Cases

### Customer Support
- View all customer conversations
- Quick response to inquiries
- Track conversation history

### Marketing Campaigns
- Send targeted messages
- Follow up with leads
- Track engagement

### Sales Team
- Manage customer relationships
- Send quotes and proposals
- Track deal progress

### Operations
- Booking confirmations
- Schedule updates
- Customer notifications

## 🔮 Future Enhancements

Planned features:
- 🔐 Built-in authentication system
- 📊 Analytics dashboard
- 🤖 AI-powered response suggestions
- 📁 File/image sending capability
- 🔔 Push notifications
- 📱 Mobile app version
- 🌍 Multi-language support
- 📅 Scheduled messages

## 📄 License

Part of the Hot Boat WhatsApp Bot project.

## 👏 Credits

**Kia-Ai** - Built with ❤️ for Hot Boat Chile

**Technologies:**
- FastAPI
- WhatsApp Business API
- Cloudflare Tunnel
- PostgreSQL

---

## 🎉 Ready to Start?

1. **Start locally:** `./start_kia_ai.sh` or `start_kia_ai.bat`
2. **Open browser:** http://localhost:8000
3. **Send your first message!**

For remote access, follow the [Quick Start Guide](KIA_AI_QUICKSTART.md).

**Questions?** Check the [Full Setup Guide](KIA_AI_SETUP.md).

---

**Made with 💚 for better customer communication**

