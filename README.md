# Perform-o-Meter — Discord Bot

A playful Discord bot that scores the "performative-ness" of members (0–100) using **real-time ChatGPT analysis**. Built with **discord.py**, **SQLAlchemy**, and **OpenAI API**.

> Real-time performative male culture detection. Opt‑in only. Fully explainable.

---

## Features
- **Real-time ChatGPT analysis**: Every message gets instantly analyzed and classified
- **Ultra-cost-effective**: Uses GPT-5 Nano (~90% cheaper than GPT-3.5-turbo)
- Slash commands: `/optin`, `/optout`, `/allow_channel`, `/deny_channel`, `/meter`, `/leaderboard`, `/why`
- Channel allowlist + per‑user opt‑in (privacy‑first)
- **Live message analysis**: Bot responds to each message with performative-ness classification
- Explainable scoring with detailed breakdowns of performative vs non-performative vs neutral messages
- SQLite database (default) with SQLAlchemy models
- Dockerfile included

---

## Quickstart (Local)

1) **Create a Discord application & bot:**
   - https://discord.com/developers/applications → *New Application* → *Bot*.
   - Toggle **MESSAGE CONTENT INTENT** and **SERVER MEMBERS INTENT**.
   - Copy the *Bot Token*.

2) **Invite the bot** to your server:
   - Under *OAuth2 → URL Generator*: scopes `bot` and `applications.commands`.
   - Bot permissions: `Send Messages`, `Embed Links`, `Read Message History`, `Add Reactions` (optional).

3) **Get OpenAI API key:**
   - Go to https://platform.openai.com/api-keys
   - Create a new API key
   - **Important**: Add payment method to avoid quota issues

4) **Clone & run**
```bash
python -m venv .venv && source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env
# edit .env with your values
python -m src.bot.bot
```

5) **First use**
- In a server channel, run `/allow_channel` (admin) to enable scoring in that channel
- Members run `/optin` to participate
- **Start chatting!** The bot will analyze every message in real-time
- Try `/meter @you` and `/leaderboard`

---

## Environment Variables (.env)
```
DISCORD_BOT_TOKEN=YOUR_TOKEN_HERE
# Optional: limit slash command sync to one guild for faster dev (copy your server ID)
GUILD_ID=123456789012345678
# SQLite by default — leave as-is or change to Postgres URL later
DB_URL=sqlite:///./performometer.db
# OpenAI API key for ChatGPT-based scoring (REQUIRED)
OPENAI_API_KEY=your_openai_api_key_here
```

> If you remove `GUILD_ID`, commands will sync globally (may take up to an hour). With `GUILD_ID`, sync is instant for that server.

---

## Real-Time ChatGPT Analysis

The bot analyzes every message in real-time using OpenAI's GPT-5 Nano (ultra-cost-effective model). Each message gets classified as:

- **🎭 PERFORMATIVE**: Shows performative male culture vibes (matcha, Clairo, "in my feels", aesthetic content)
- **💪 NON-PERFORMATIVE**: Shows toxically masculine vibes (dark humor, misogyny, "sigma male" content)  
- **😐 NEUTRAL**: Neither performative nor non-performative

### How It Works
1. **User sends message** in an allowed channel
2. **Bot instantly analyzes** with ChatGPT
3. **Bot responds immediately** with colored embed showing the classification
4. **Message is stored** for future scoring calculations

### Scoring System
- **Base score**: 50/100
- **Performative messages**: +1 point each
- **Non-performative messages**: -1 point each
- **Neutral messages**: 0 points
- **Final score**: 50 + (total adjustments × 2), capped at 0-100

### OpenAI API Setup
1. **Get API key**: https://platform.openai.com/api-keys
2. **Add payment method**: Required to avoid quota errors
3. **Add to .env**: `OPENAI_API_KEY=your_key_here`
4. **Install dependencies**: `pip install -r requirements.txt`

**💰 Cost-Effective**: Uses GPT-5 Nano ($0.05/1M input tokens, $0.40/1M output tokens) - ~90% cheaper than GPT-3.5-turbo!

**⚠️ Important**: You need a valid OpenAI API key with billing set up. The bot will show quota errors without it.

---

## Commands

### User Commands
- `/optin` - Opt in to analysis (all users are automatically included)
- `/optout` - Opt out of analysis
- `/meter @user [days]` - Show user's performative-ness score
- `/leaderboard [days]` - Show top performers
- `/why @user [days]` - Detailed breakdown of user's score

### Admin Commands
- `/allow_channel` - Enable analysis in current channel
- `/deny_channel` - Disable analysis in current channel
- `/config_show` - Show current configuration
- `/config_set key value` - Update configuration

---

## Troubleshooting

### "ChatGPT API error: 429 - insufficient_quota"
**Solution**: Add a payment method to your OpenAI account at https://platform.openai.com/account/billing

### Bot not responding to messages
**Check**:
1. Bot has `MESSAGE CONTENT INTENT` enabled
2. Channel is allowed with `/allow_channel`
3. User has opted in with `/optin`
4. OpenAI API key is valid

### Getting only "NEUTRAL" responses
**Solution**: The prompt has been optimized to be more decisive. Try messages with clear performative or toxic indicators.

---

## Config (config.yaml)

The bot now primarily uses ChatGPT analysis, but you can still adjust the legacy heuristic weights:

```yaml
weights:
  aesthetic: 0.10
  text_vibe: 0.35
  links_media: 0.25
  self_presentation: 0.10
  engagement: 0.10
  sincerity: 0.10

decay:
  half_life_days: 7

tokens:
  beverages: [matcha, chai, cortado, oatly]
  books: ["bell hooks", "Sally Rooney", "Ocean Vuong", Murakami]
  aesthetic: [liminal, cozy, ghibli, "photo dump", "soft launch"]
  accessories: [tote, "wired headphones", sambas, birks, "silver ring"]
  music: [Laufey, Clairo, Boygenius, "Phoebe Bridgers"]
```

---

## Docker
```bash
docker build -t performometer .
docker run --env-file .env -v $(pwd)/data:/app/data --name performometer --rm performometer
```

---

## Notes & Limits
- **Real-time analysis**: Bot responds to every message (may increase API usage)
- **OpenAI costs**: Each message analysis costs ~$0.00001-0.00005 (GPT-5 Nano pricing)
- **Rate limiting**: Consider adding cooldowns for high-traffic servers
- **Privacy**: Bot only analyzes messages in allowed channels from opted-in users
- **Fallback**: Bot includes heuristic analysis as backup when ChatGPT fails
- **Cost savings**: GPT-5 Nano is ~90% cheaper than GPT-3.5-turbo for this use case

MIT License.