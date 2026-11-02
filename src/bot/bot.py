from __future__ import annotations
import os, re, json, logging
from datetime import datetime
from typing import List

import discord
from discord import app_commands
from dotenv import load_dotenv
from sqlalchemy.orm import Session

from .db import SessionLocal, initialize_database
from .models import User, Message, ChannelConfig
from .config import get_config, set_config_key
from .scoring import compute_user_score_chatgpt, emoji_density

load_dotenv()

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")
GUILD_ID = int(GUILD_ID) if GUILD_ID and GUILD_ID.isdigit() else None

INTENTS = discord.Intents.default()
INTENTS.message_content = True
INTENTS.members = True

bot = discord.Client(intents=INTENTS, allowed_mentions=discord.AllowedMentions.none())
tree = app_commands.CommandTree(bot)

@tree.error
async def command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    # discord.py's default command handler logs exception bodies and SQL parameters.
    logging.getLogger(__name__).warning("Slash command failed.")
    text = ("Manage Server permission is required." if isinstance(error, app_commands.MissingPermissions)
            else "Command unavailable. Please try again later or contact the bot operator.")
    try:
        if interaction.response.is_done():
            await interaction.followup.send(text, ephemeral=True)
        else:
            await interaction.response.send_message(text, ephemeral=True)
    except discord.HTTPException:
        logging.getLogger(__name__).warning("Command error response could not be delivered.")


# ---- Helpers ----

def get_or_create_user(session: Session, discord_user_id: int, username: str = None) -> User:
    user = session.get(User, discord_user_id)
    if user is None:
        user = User(id=discord_user_id, opted_in=False)
        session.add(user)
        session.flush()
    return user


def scoring_channels(session, interaction):
    # Channel IDs scope storage to the guild and prevent disclosure across private channels.
    if interaction.guild is None:
        return []
    visible = {c.id for c in interaction.guild.channels
               if c.permissions_for(interaction.user).view_channel
               and c.permissions_for(interaction.user).read_message_history}
    return [r.channel_id for r in session.query(ChannelConfig).filter_by(allowed=True)
            if r.channel_id in visible]


async def ensure_channel_allowed(session: Session, channel_id: int) -> bool:
    row = session.get(ChannelConfig, channel_id)
    return bool(row and row.allowed)

def extract_links(text: str) -> List[str]:
    return re.findall(r'https?://\S+', text or "")

# ---- Events ----

@bot.event
async def on_ready():
    # Sync slash commands fast on a single guild during dev
    if GUILD_ID:
        guild = discord.Object(id=GUILD_ID)
        tree.copy_global_to(guild=guild)
        await tree.sync(guild=guild)
        print("Guild commands synced.")
    else:
        await tree.sync()
        print("Global command sync initiated (may take time).")
    print("Discord client ready.")

@bot.event
async def on_message(message: discord.Message):
    try:
        if (message.author.bot or message.guild is None or message.webhook_id
                or isinstance(message.channel, discord.Thread)):
            return

        with SessionLocal() as session:
            # Only log from allowed channels
            if not await ensure_channel_allowed(session, message.channel.id):
                return
            user = session.get(User, message.author.id)
            if not user or not user.opted_in or user.consented_at is None:
                return

            # Store minimal message features
            # Only domains needed by heuristic scoring; discard URL paths/query strings.
            from urllib.parse import urlsplit
            links = [f"https://{urlsplit(url).hostname}" for url in extract_links(message.content or "")]
            images = int(any(a.content_type and a.content_type.startswith("image/") for a in message.attachments))
            emojis = emoji_density(message.content or "")
            reactions = sum([r.count for r in message.reactions]) if message.reactions else 0

            m = Message(
                user_id=user.id,
                channel_id=message.channel.id,
                created_at=datetime.utcnow(),
                text=message.content or "",
                links=links,
                emojis=emojis,
                images=images,
                reactions=reactions
            )
            session.add(m)
            user.last_seen_at = datetime.utcnow()
            session.commit()

    except Exception:
        # Never print exception bodies, message content, or identifiers.
        logging.getLogger(__name__).warning("Message processing failed.")

# ---- Commands ----

@tree.command(name="optin", description="Consent to storing future messages and OpenAI scoring in allowed channels")
@app_commands.guild_only()
async def optin(interaction: discord.Interaction):
    with SessionLocal() as session:
        user = get_or_create_user(session, interaction.user.id)
        if not user.opted_in or user.consented_at is None:
            user.consented_at = datetime.utcnow()
        user.opted_in = True
        session.commit()
    await interaction.response.send_message("Opted in across servers: future messages in enabled channels are stored and may be sent to OpenAI for scores. Aggregate scores may appear on leaderboards. `/optout` stops future processing; contact the bot operator for stored-data removal.", ephemeral=True)

@tree.command(name="optout", description="Opt out of Perform-o-Meter")
@app_commands.guild_only()
async def optout(interaction: discord.Interaction):
    with SessionLocal() as session:
        user = get_or_create_user(session, interaction.user.id)
        user.opted_in = False
        user.consented_at = None
        session.commit()
    await interaction.response.send_message("Opted out across servers. Collection and scoring are stopped. Existing data is retained but excluded; contact the bot operator to request removal.", ephemeral=True)

@tree.command(name="allow_channel", description="Allow scoring in this channel (admin)")
@app_commands.guild_only()
@app_commands.checks.has_permissions(manage_guild=True)
async def allow_channel(interaction: discord.Interaction):
    if isinstance(interaction.channel, discord.Thread):
        await interaction.response.send_message("Enable a regular server channel; threads are not supported.", ephemeral=True)
        return
    with SessionLocal() as session:
        row = session.get(ChannelConfig, interaction.channel.id)
        if row is None:
            row = ChannelConfig(channel_id=interaction.channel.id, allowed=True)
            session.add(row)
        else:
            row.allowed = True
        session.commit()
    await interaction.response.send_message(f"Enabled scoring in {interaction.channel.mention}")

@tree.command(name="deny_channel", description="Disable scoring in this channel (admin)")
@app_commands.guild_only()
@app_commands.checks.has_permissions(manage_guild=True)
async def deny_channel(interaction: discord.Interaction):
    with SessionLocal() as session:
        row = session.get(ChannelConfig, interaction.channel.id)
        if row is None:
            row = ChannelConfig(channel_id=interaction.channel.id, allowed=False)
            session.add(row)
        else:
            row.allowed = False
        session.commit()
    await interaction.response.send_message(f"Disabled scoring in {interaction.channel.mention}")

@tree.command(name="meter", description="Show a performative-ness score")
@app_commands.guild_only()
@app_commands.describe(member="User to score", days="Window in days (1-60)")
async def meter(interaction: discord.Interaction, member: discord.Member, days: app_commands.Range[int,1,60]=14):
    await interaction.response.defer(ephemeral=True)
    with SessionLocal() as session:
        score, info = compute_user_score_chatgpt(session, member.id, days=days, channel_ids=scoring_channels(session, interaction), guild_id=interaction.guild_id)

    # Create embed with ChatGPT analysis results
    embed = discord.Embed(
        title=f"Perform-o-Meter: {member.display_name}",
        description=f"Score (last {days}d): **{score}/100**",
        color=discord.Color.blurple()
    )

    # Add ChatGPT analysis breakdown
    embed.add_field(name="Total Messages", value=str(info.get("total_messages", 0)), inline=True)
    embed.add_field(name="Performative", value=str(info.get("performative_messages", 0)), inline=True)
    embed.add_field(name="Non-Performative", value=str(info.get("non_performative_messages", 0)), inline=True)
    embed.add_field(name="Neutral", value=str(info.get("neutral_messages", 0)), inline=True)
    embed.add_field(name="Raw Score", value=str(info.get("raw_score", 0)), inline=True)
    embed.add_field(name="Analysis", value=info.get("chatgpt_analysis", "No analysis"), inline=True)


    await interaction.followup.send(embed=embed)

@tree.command(name="leaderboard", description="Scores for consenting members in visible enabled channels")
@app_commands.guild_only()
@app_commands.describe(days="Window in days (1-60)")
async def leaderboard(interaction: discord.Interaction, days: app_commands.Range[int,1,60]=14):
    # Compute on-demand for all guild members, but only include those with existing data
    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild
    with SessionLocal() as session:
        channel_ids = scoring_channels(session, interaction)
        rows = []
        for m in guild.members:
            if m.bot:
                continue
            # Only include users who already exist in the database (have been analyzed)
            user = session.get(User, m.id)
            if user and user.opted_in and user.consented_at is not None:
                score, info = compute_user_score_chatgpt(session, m.id, days=days, channel_ids=channel_ids, guild_id=interaction.guild_id)
                if info.get("total_messages", 0):
                    rows.append((discord.utils.escape_markdown(m.display_name), score))

    rows.sort(key=lambda x: x[1], reverse=True)
    lines = [f"**{i+1}.** {name} — **{score}**" for i,(name,score) in enumerate(rows[:15])]
    msg = "\n".join(lines) or "No eligible activity. Members can participate with `/optin`."
    await interaction.followup.send(f"**Leaderboard (last {days}d)**\n{msg}")

@tree.command(name="why", description="Explain a user's score")
@app_commands.guild_only()
@app_commands.describe(member="User to explain", days="Window in days (1-60)")
async def why(interaction: discord.Interaction, member: discord.Member, days: app_commands.Range[int,1,60]=14):
    await interaction.response.defer(ephemeral=True)
    with SessionLocal() as session:
        score, info = compute_user_score_chatgpt(session, member.id, days=days, channel_ids=scoring_channels(session, interaction), guild_id=interaction.guild_id)

    # Create detailed explanation with ChatGPT analysis
    text = f"**{member.display_name} — {score}/100 (last {days}d)**\n\n"
    text += f"**ChatGPT Analysis:**\n"
    text += f"• Total Messages: {info.get('total_messages', 0)}\n"
    text += f"• Performative: {info.get('performative_messages', 0)}\n"
    text += f"• Non-Performative: {info.get('non_performative_messages', 0)}\n"
    text += f"• Neutral: {info.get('neutral_messages', 0)}\n"
    text += f"• Raw Score: {info.get('raw_score', 0)}\n\n"

    text += info.get("chatgpt_analysis", "No eligible messages")
    await interaction.followup.send(text)

# ---- Config commands ----

@tree.command(name="config_show", description="Show current scoring config")
@app_commands.guild_only()
async def config_show(interaction: discord.Interaction):
    with SessionLocal() as session:
        cfg = get_config(session, guild_id=interaction.guild_id)
    pretty = json.dumps(cfg, indent=2, ensure_ascii=False)
    await interaction.response.send_message(f"```json\n{pretty}\n```", ephemeral=True)

@tree.command(name="config_set_weight", description="Set weight for a category")
@app_commands.guild_only()
@app_commands.describe(category="One of: aesthetic, text_vibe, links_media, self_presentation, engagement, sincerity",
                       value="0.0 to 1.0 (weights need not sum to 1)")
@app_commands.checks.has_permissions(manage_guild=True)
async def config_set_weight(interaction: discord.Interaction, category: str, value: app_commands.Range[float, 0.0, 1.0]):
    with SessionLocal() as session:
        cfg = get_config(session, guild_id=interaction.guild_id)
        weights = cfg.get("weights", {})
        if category not in weights:
            await interaction.response.send_message(f"Unknown category '{category}'.", ephemeral=True)
            return
        weights[category] = float(value)
        set_config_key("weights", weights, session, guild_id=interaction.guild_id)
    await interaction.response.send_message(f"Updated `{category}` weight to {value}.", ephemeral=True)

@tree.command(name="config_tokens_add", description="Add a token to a group")
@app_commands.guild_only()
@app_commands.describe(group="e.g., beverages, books, aesthetic, accessories, music", token="The word/phrase to add")
@app_commands.checks.has_permissions(manage_guild=True)
async def config_tokens_add(interaction: discord.Interaction, group: str, token: str):
    with SessionLocal() as session:
        cfg = get_config(session, guild_id=interaction.guild_id)
        tokens = cfg.get("tokens", {})
        lst = tokens.get(group, [])
        if token in lst:
            await interaction.response.send_message("Token already present.", ephemeral=True)
            return
        lst.append(token)
        tokens[group] = lst
        set_config_key("tokens", tokens, session, guild_id=interaction.guild_id)
    await interaction.response.send_message(f"Added token '{token}' to '{group}'.", ephemeral=True)

@tree.command(name="config_tokens_remove", description="Remove a token from a group")
@app_commands.guild_only()
@app_commands.describe(group="e.g., beverages, books, aesthetic, accessories, music", token="The word/phrase to remove")
@app_commands.checks.has_permissions(manage_guild=True)
async def config_tokens_remove(interaction: discord.Interaction, group: str, token: str):
    with SessionLocal() as session:
        cfg = get_config(session, guild_id=interaction.guild_id)
        tokens = cfg.get("tokens", {})
        lst = tokens.get(group, [])
        if token not in lst:
            await interaction.response.send_message("Token not found.", ephemeral=True)
            return
        lst = [t for t in lst if t != token]
        tokens[group] = lst
        set_config_key("tokens", tokens, session, guild_id=interaction.guild_id)
    await interaction.response.send_message(f"Removed token '{token}' from '{group}'.", ephemeral=True)

# ---- Entrypoint ----
if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("DISCORD_BOT_TOKEN missing. Put it in .env or env vars.")
    initialize_database()
    bot.run(TOKEN)
