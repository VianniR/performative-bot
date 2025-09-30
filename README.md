# Perform-o-Meter — Discord Bot

A playful, opt‑in bot that scores the “performative‑ness” of members (0–100) using transparent, configurable heuristics. Built with **discord.py**, **SQLAlchemy**, and **YAML** config.

> Party game vibes. Opt‑in only. Fully explainable.

---

## Features
- Slash commands: `/optin`, `/optout`, `/allow_channel`, `/deny_channel`, `/meter`, `/leaderboard`, `/why`, `/config show`, `/config set …`
- Channel allowlist + per‑user opt‑in (privacy‑first).
- **ChatGPT-powered scoring**: Uses OpenAI's GPT-3.5-turbo to analyze messages for performative-ness
- Explainable scoring with detailed breakdowns of performative vs sincere vs neutral messages
- SQLite database (default) with SQLAlchemy models.
- Dockerfile included.

---

## Quickstart (Local)

1) **Create a Discord application & bot:**
   - https://discord.com/developers/applications → *New Application* → *Bot*.
   - Toggle **MESSAGE CONTENT INTENT** and **SERVER MEMBERS INTENT**.
   - Copy the *Bot Token*.

2) **Invite the bot** to your server:
   - Under *OAuth2 → URL Generator*: scopes `bot` and `applications.commands`.
   - Bot permissions: `Send Messages`, `Embed Links`, `Read Message History`, `Add Reactions` (optional).

3) **Clone & run**
```bash
python -m venv .venv && source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env
# edit .env with your values
python -m src.bot.bot
```

4) **First use**
- In a server channel, run `/allow_channel` (admin) to enable scoring in that channel.
- Members run `/optin` to participate.
- Try `/meter @you` and `/leaderboard`.

---

## Environment Variables (.env)
```
DISCORD_BOT_TOKEN=YOUR_TOKEN_HERE
# Optional: limit slash command sync to one guild for faster dev (copy your server ID)
GUILD_ID=123456789012345678
# SQLite by default — leave as-is or change to Postgres URL later
DB_URL=sqlite:///./performometer.db
# OpenAI API key for ChatGPT-based scoring
OPENAI_API_KEY=your_openai_api_key_here
```

> If you remove `GUILD_ID`, commands will sync globally (may take up to an hour). With `GUILD_ID`, sync is instant for that server.

## ChatGPT Integration

The bot now uses OpenAI's GPT-3.5-turbo to analyze messages for performative-ness. Each message is classified as:

- **PERFORMATIVE**: Trying to present a curated, aesthetic, or "main character" image
- **SINCERE**: Genuine, casual, or authentic communication  
- **NEUTRAL**: Neither particularly performative nor sincere

### Scoring System
- Base score: 50/100
- Performative messages: +1 point each
- Sincere messages: -1 point each
- Neutral messages: 0 points
- Final score: 50 + (total adjustments × 2), capped at 0-100

### Setup
1. Get an OpenAI API key from https://platform.openai.com/api-keys
2. Add `OPENAI_API_KEY=your_key_here` to your `.env` file
3. Install dependencies: `pip install -r requirements.txt`

The bot will automatically use ChatGPT scoring when the API key is configured.

---

## Config (config.yaml)

Adjust weights, decay, and token lists:
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

You can also edit these at runtime with `/config set`.

---

## Docker
```bash
docker build -t performometer .
docker run --env-file .env -v $(pwd)/data:/app/data --name performometer --rm performometer
```

---

## Notes & Limits
- This is a **toy** scoring system. All rules are explainable and editable.
- By default, the bot only analyzes messages in **allowed channels** and from **opted-in** users.
- In large servers, you may want Postgres and background jobs; swap `DB_URL` accordingly.

MIT License.
