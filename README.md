# Perform-o-Meter

A Python Discord bot that classifies participating members' messages with an LLM and turns those classifications into behavior scores and server leaderboards. The project combines Discord slash commands, a SQLAlchemy message pipeline, configurable heuristic scoring, and an OpenAI integration.

The labels are a playful interpretation of “performative” culture, not a reliable assessment of personality, sincerity, identity, or misconduct. The prompt contains subjective stereotypes; this is not a moderation system.

## Implemented features

- Explicit user consent and administrator-controlled channel allowlists.
- On-demand scores and classification breakdowns over a 1–60 day window.
- Leaderboards for consenting members, limited to the current server and channels the requester can read.
- SQLAlchemy persistence with SQLite by default and non-destructive startup.
- A configurable LLM model and a weighted, time-decayed heuristic fallback.
- Per-server heuristic configuration through slash commands.

Automatic message replies are disabled. Messages are collected after consent; LLM analysis happens when someone requests `/meter`, `/why`, or `/leaderboard`. There are no verified performance benchmarks in this repository. The author's resume reports use by 100+ users; that figure has not been independently verified by this code review.

## Stack and architecture

Python 3.10+, discord.py, SQLAlchemy 2, python-dotenv, PyYAML, and the OpenAI Python SDK. The Docker image uses Python 3.11.

```text
Discord message
  → reject bots, webhooks, and DMs
  → check channel allowlist and fresh explicit user consent
  → persist text and minimal scoring features in SQLAlchemy

Score command
  → check consent again
  → select post-consent messages within the requested time window
  → restrict to current-server, readable, currently enabled channels
  → classify up to 10 recent messages with OpenAI
  → aggregate score, or use heuristics if none can be classified
  → return an ephemeral aggregate response (no message excerpts)
```

| Module | Responsibility |
| --- | --- |
| `src/bot/bot.py` | Discord events, consent, channel permissions, slash commands |
| `src/bot/models.py` | Users, messages, channels, configuration, legacy score table |
| `src/bot/db.py` | Engine, sessions, additive initialization |
| `src/bot/scoring.py` | Consent-aware selection, classification, score aggregation, fallback |
| `src/bot/config.py` | YAML defaults and server-specific database overrides |

One process can serve multiple communities. Channel snowflakes identify each message's source; score commands resolve channel IDs through the current guild. Consent is **global across every server served by this instance**, while channel allowlists and new configuration overrides are server-specific. Threads are not included in score queries or supported as collection channels by the documented setup.

## Local setup

1. Create a bot in the [Discord Developer Portal](https://discord.com/developers/applications). Enable Message Content and Server Members privileged intents in its Bot settings.
2. Invite it to a test server with `bot` and `applications.commands` scopes. Grant View Channels, Send Messages, and Embed Links in the channels you intend to use. Score queries also require the requester to have Read Message History.
3. From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env locally; never commit credentials.
```

4. For an existing installation, stop the bot and make a protected database backup before starting this version. Startup adds missing `username` and `consented_at` columns and creates missing tables. It does not drop tables, reset preferences, or delete records. This small additive migration supports the known legacy schema; future schema changes should use versioned migrations (for example Alembic), tested against a backup first.
5. When ready to connect to your test server:

```bash
python -m src.bot.bot
```

6. A member with Manage Server permission runs `/allow_channel` in a regular server channel. Each participant runs `/optin` before collection begins. Try `/meter`, `/why`, and `/leaderboard` after sending new messages.

Importing the bot does not initialize or open a database or connect to Discord. Running its module as the entrypoint does initialize the configured database and connect. The automated tests below mock that connection.

## Environment variables

| Variable | Required | Purpose/default |
| --- | --- | --- |
| `DISCORD_BOT_TOKEN` | Yes, to run the bot | Discord bot credential |
| `OPENAI_API_KEY` | For LLM scoring | Absent/unavailable API falls back to heuristics |
| `OPENAI_MODEL` | No | `gpt-4.1-mini` |
| `DB_URL` | No | `sqlite:///./performometer.db`, relative to working directory |
| `CONFIG_PATH` | No | `config.yaml`, relative to working directory |
| `GUILD_ID` | No | Numeric test server ID for guild command registration; omit for global sync |

Environment variables take precedence over `.env`. Never put credentials in `config.yaml`. The model default supports [Chat Completions](https://developers.openai.com/api/docs/models/gpt-4.1-mini); account access and API availability must be checked separately before live use. Custom models must accept the existing `max_tokens` and `temperature` parameters. Changing a model can change classifications.

## Database and scoring

`users` stores Discord user IDs, preference state, explicit consent time, and activity timestamps. The nullable legacy username column is preserved but new processing does not populate it. `messages` stores text, user/channel IDs, ingestion time, linked domains, emoji density, an image-presence flag, and initial reaction count. Attachment files are not downloaded. Later reactions and message edits/deletions are not synchronized.

For LLM scoring, the newest 10 eligible messages are sampled; text shorter than three trimmed characters is skipped. Labels contribute +1 (performative), −1 (non-performative), or 0 (neutral). The existing formula is preserved:

```text
score = clamp(50 + 1.5 × sum(successful label adjustments), 0, 100)
```

With a ten-message sample, successful LLM scores range from 35 to 65. No eligible messages yields 0 with a “No eligible messages” explanation. Failed classifications are excluded; if all classifications are unavailable or skipped, the bot uses the existing weighted heuristic calculation. Partial failures are visible in the analyzed/sample counts. A pre-existing substring rule for fraternity/sorority terms is retained. Classification output is probabilistic and repeated requests can differ.

The fallback measures configured token hits, selected media domains, image presence, reaction count, and message length, using time decay (default half-life: seven days). Its `aesthetic` component currently remains zero. YAML weights affect only this fallback. New database overrides are namespaced per server; legacy global overrides remain read-only defaults.

The legacy `scores` table is preserved but no longer read or written. Its cache omitted consent, server/channel scope, and expiry, so reusing it could expose old data or stale scores. New score responses contain aggregates, not stored message examples.

## Commands

All commands run in servers. Consent changes, configuration responses, scores, explanations, and leaderboards are ephemeral.

| Command | Action | Permission |
| --- | --- | --- |
| `/optin` | Consent to collection of future messages and on-demand OpenAI analysis across this instance's servers | Member |
| `/optout` | Stop collection and exclude stored messages from all score paths | Member |
| `/meter member [days]` | Aggregate score; default 14 days, range 1–60 | Member |
| `/why member [days]` | Classification counts and analysis status, without message quotes | Member |
| `/leaderboard [days]` | Top 15 eligible members in accessible, enabled channels | Member |
| `/allow_channel` | Enable collection in the current channel | Manage Server |
| `/deny_channel` | Disable collection and exclude the channel from score queries | Manage Server |
| `/config_show` | Display current server's effective heuristic configuration | Member |
| `/config_set_weight category value` | Set a fallback category weight between 0 and 1 | Manage Server |
| `/config_tokens_add group token` | Add a fallback matching token | Manage Server |
| `/config_tokens_remove group token` | Remove a fallback matching token | Manage Server |

## Privacy and data handling

- **Fresh consent is required.** Legacy automatically-created `opted_in=True` flags are insufficient. Existing messages remain untouched and are excluded. `/optin` establishes a new starting timestamp; re-opting in after opting out excludes older messages again. Repeating `/optin` while already opted in preserves the timestamp.
- **Excluded users are not tracked.** Their messages do not create user records, update activity, store features, or reach OpenAI. `/optout` itself retains a minimal preference record. DMs, bot messages, webhooks, and non-allowed channels are ignored.
- **External processing:** score commands can submit participating users' stored message text to OpenAI, even when another member requests the score. No Discord IDs or display names are added to the API prompt, but message text can itself contain personal information, mentions, URLs, or secrets. `store=False` is used; this is not a guarantee of zero provider retention. Operators must review the provider's applicable data policies and communicate them before collecting messages.
- **Local minimization:** no new username storage, no persisted classification cache or quoted examples, and link-feature storage contains domains rather than URL paths or query strings. Raw text still contains any URLs originally written. Logs intentionally omit message text, identifiers, credentials, and exception bodies; do not enable HTTP/SDK debug logging on real traffic.
- **Retention:** there is no automatic purge. The 60-day maximum scoring window limits reads, not physical storage. Existing user/message/cache records have not been deleted or rewritten by this update. Operators must establish and communicate a retention period, protect the database and backups, and implement an approved cleanup procedure before further production collection.
- **Removal requests:** run `/optout`, then contact the operator who hosts the bot (ask your server administrator to identify them). Request removal of your Discord user ID, associated messages, legacy username and cached scores, and ask about backup expiry. There is no self-service deletion command. The operator must verify the requester and arrange deletion separately; opting out alone does not erase data or retract prior API requests.
- **Visibility:** aggregate scores may be requested by other members. Responses are ephemeral and use only enabled channels the requester can view and read; message excerpts are never displayed. Snowflake identifiers are still personal data and must not be published in screenshots or database exports.

## Offline validation

```bash
python -m unittest discover -s tests -v
python -m pip check
python scripts/scan_secrets.py
```

Tests disable dotenv loading, use synthetic records and temporary databases, and mock Discord login and OpenAI calls. They cover consent, collection, command responses, scope restrictions, additive migration/restart persistence, sample size, score arithmetic, fallback, and model configuration. No real credentials are required.

The secret scanner examines locally reachable Git history and current tracked/unignored files using token patterns plus private comparisons with local `.env` credential values. It prints locations/types only. It is heuristic, not proof of absence, and does not inspect remote-only refs, GitHub artifacts, issues, or unreachable objects. Review findings manually; do not paste credentials into reports. `.gitignore` does not erase history.

## Docker

`.dockerignore` excludes local credentials, databases, and Git history. The image defaults to a database in `/app/data`; mount a persistent volume:

```bash
docker build -t performometer .
docker run --rm --env-file .env \
  -e DB_URL=sqlite:////app/data/performometer.db \
  -v "$(pwd)/data:/app/data" performometer
```

The explicit `DB_URL` prevents a local `.env` value from placing the database outside the mounted directory. Treat `.env`, the mounted directory, and backups as private.

## Demo placeholders

- Score/explanation screenshot: pending; capture only synthetic messages and anonymized members.
- Leaderboard screenshot: pending; use a test server with consenting test participants.
- Short demo: pending; show `/optin`, administrator channel setup, a score, and `/optout`.

## Known limitations and next steps

API calls and database work remain synchronous inside command handlers. Large leaderboards can block the event loop or exceed interaction deadlines. There is no request cooldown, global API budget, or persistent safe cache; repeated score requests incur API cost. Use a controlled test server before further production operation, and address workload limits before scaling. Cross-process concurrent consent changes are not coordinated; run one bot process per database.

No live Discord or OpenAI calls, production database inspection/migration, deployment, commits, pushes, credential rotation, or history rewriting were performed during this hardening pass. See [the audit notes](AUDIT.md) for verification scope and remaining operator tasks.
