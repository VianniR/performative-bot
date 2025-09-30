# Perform-o-Meter — Discord Bot

A playful, opt‑in bot that scores the “performative‑ness” of members (0–100) using transparent, configurable heuristics. Built with **discord.py**, **SQLAlchemy**, and **YAML** config.

> Party game vibes. Opt‑in only. Fully explainable.

---

## Features
- Slash commands: `/optin`, `/optout`, `/allow_channel`, `/deny_channel`, `/meter`, `/leaderboard`, `/why`, `/config show`, `/config set …`
- Channel allowlist + per‑user opt‑in (privacy‑first).
- Explainable scoring with weights and token lists (editable in `config.yaml` or via `/config set`).
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
```

> If you remove `GUILD_ID`, commands will sync globally (may take up to an hour). With `GUILD_ID`, sync is instant for that server.

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
