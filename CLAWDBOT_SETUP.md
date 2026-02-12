# ClawdBot Setup Guide

ClawdBot lets people text your number and get AI guidance instantly.

## Quick Start

### 1. Get Your Twilio Credentials

Your credentials are already in `.env`:
```bash
TWILIO_ACCOUNT_SID=your-account-sid
TWILIO_AUTH_TOKEN=your-auth-token
TWILIO_PHONE_NUMBER=your-phone-number
```

### 2. Set Up WhatsApp (Optional)

**For Testing (5 minutes):**
1. Go to [Twilio Console](https://console.twilio.com/) → Messaging → Try WhatsApp
2. You'll get a sandbox number (e.g., `+1 415 523 8886`)
3. Send `join <code>` to that number from your phone
4. Update `.env`: `TWILIO_WHATSAPP_NUMBER=+14155238886`

**For Production:**
1. Request WhatsApp Business number from Twilio
2. Go through Meta verification (~2-3 days)
3. Update `.env` with your approved WhatsApp number

### 3. Run ClawdBot Locally

```bash
cd /Users/boraelkin/Desktop/psy/Hedge
source .venv/bin/activate
python clawdbot.py
```

Server will start on http://localhost:8000

### 4. Expose Your Webhook

Twilio needs a public URL to send messages to. Options:

**A. Using ngrok (Fastest for testing):**
```bash
# Install ngrok
brew install ngrok

# Expose local server
ngrok http 8000
```

You'll get a URL like: `https://abc123.ngrok.io`

**B. Deploy to production:**
- Railway: `railway up`
- Render: Connect GitHub repo
- Fly.io: `fly deploy`
- Your own server with HTTPS

### 5. Configure Twilio Webhook

1. Go to [Twilio Console](https://console.twilio.com/)
2. Navigate to **Phone Numbers** → **Manage** → **Active Numbers**
3. Click your phone number (+12272329147)

**For SMS:**
4. Scroll to **Messaging Configuration**
5. Under "A MESSAGE COMES IN":
   - Webhook: `https://your-domain.com/webhooks/twilio`
   - HTTP POST
6. Click **Save**

**For WhatsApp:**
7. Go to **Messaging** → **Try it out** → **WhatsApp**
8. Under "WHEN A MESSAGE COMES IN":
   - Webhook: `https://your-domain.com/webhooks/twilio`
   - HTTP POST
9. Click **Save**

### 6. Test It!

**SMS Test:**
```
Text your Twilio number: +12272329147
Message: "Hi"
```

**WhatsApp Test:**
```
Message your WhatsApp sandbox: +14155238886
Message: "Hi"
```

You should get a response from ClawdBot!

---

## How It Works

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│    User      │────▶│   Twilio     │────▶│  ClawdBot    │
│  (texts you) │     │  (forwards)  │     │  (responds)  │
└──────────────┘     └──────────────┘     └──────────────┘
                                                  │
                                                  ▼
                                          ┌──────────────┐
                                          │  Guide AI    │
                                          │  (Claude)    │
                                          └──────────────┘
```

1. User texts your Twilio number
2. Twilio forwards to your webhook
3. ClawdBot receives and processes
4. Guide AI analyzes (with vision if image)
5. Response sent back via Twilio
6. User gets AI guidance instantly

---

## Usage Examples

**Starting a conversation:**
```
User: "Hi"
ClawdBot: "👋 Hi! I'm ClawdBot, your AI work assistant.
           What are you working on?"
```

**Asking for help:**
```
User: "How do I replace an air filter?"
ClawdBot: "I'll walk you through it step by step:
           1. Turn off your HVAC system
           2. Locate the air filter compartment..."
```

**Sending a photo:**
```
User: [sends photo of HVAC unit]
      "Which valve should I turn?"
ClawdBot: "I can see your system. Turn the valve on the
           right side - it's the blue one closest to..."
```

---

## Production Deployment

### Environment Variables

Make sure these are set in production:

```bash
ANTHROPIC_API_KEY=your-key
TWILIO_ACCOUNT_SID=your-sid
TWILIO_AUTH_TOKEN=your-token
TWILIO_PHONE_NUMBER=+12272329147
TWILIO_WHATSAPP_NUMBER=+14155238886  # optional
HOST=0.0.0.0
PORT=8000
```

### Deploy Commands

**Railway:**
```bash
railway login
railway init
railway up
```

**Render:**
- Connect GitHub repo
- Auto-deploys on push

**Docker:**
```bash
docker build -t clawdbot .
docker run -p 8000:8000 --env-file .env clawdbot
```

### Health Checks

```bash
# Basic health
curl https://your-domain.com/health

# Response:
{
  "status": "healthy",
  "twilio_configured": true,
  "sessions": 5,
  "procedures": 3
}
```

---

## Customization

### Add Custom Responses

Edit `clawdbot.py`:

```python
if text == "prices":
    return OutgoingMessage(
        recipient_id=incoming.sender_id,
        text="Our rates: $50/hr for HVAC, $75/hr for plumbing..."
    )
```

### Add More Procedures

```python
from guide.core.knowledge import Procedure, Step

knowledge_base.add_procedure(Procedure(
    id="fix-leak",
    name="Fix a Leak",
    steps=[
        Step(1, "Turn off water main"),
        Step(2, "Locate the leak"),
        # ...
    ]
))
```

### Multi-language Support

```python
# Detect language and respond accordingly
if "hola" in text.lower():
    return OutgoingMessage(
        recipient_id=incoming.sender_id,
        text="¡Hola! Soy ClawdBot..."
    )
```

---

## Troubleshooting

**Webhook not receiving messages:**
- Check Twilio console → Debugger for errors
- Verify webhook URL is correct and publicly accessible
- Test with `curl https://your-domain.com/webhooks/twilio`

**Messages not sending:**
- Check Twilio logs
- Verify account has credits
- Check recipient number format

**AI not responding:**
- Check `ANTHROPIC_API_KEY` is set
- View server logs for errors
- Test Guide separately

---

## Costs

**Twilio:**
- SMS: ~$0.0075 per message
- WhatsApp: ~$0.005 per conversation
- Phone number: ~$1/month

**Claude API:**
- Varies by usage
- Vision calls cost more than text

**Hosting:**
- Railway/Render free tier: $0
- Paid: ~$5-10/month

**Total:** ~$10-20/month for moderate usage

---

## Next Steps

1. ✅ Test locally with ngrok
2. ✅ Verify SMS and WhatsApp work
3. ✅ Deploy to production
4. ✅ Configure webhooks
5. ✅ Share number with your team
6. 🚀 Start helping people!

Questions? Check the logs or Twilio console debugger.
