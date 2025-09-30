from __future__ import annotations
import os, re, json, asyncio
from datetime import datetime
from typing import List, Optional

import discord
from discord import app_commands
from dotenv import load_dotenv
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from .db import Base, engine, SessionLocal
from .models import User, Message, ChannelConfig, Score
from .config import get_config, set_config_key
from .scoring import compute_user_score, compute_user_score_chatgpt, emoji_density, analyze_message_with_chatgpt

load_dotenv()

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")
GUILD_ID = int(GUILD_ID) if GUILD_ID and GUILD_ID.isdigit() else None

INTENTS = discord.Intents.default()
INTENTS.message_content = True
INTENTS.members = True

bot = discord.Client(intents=INTENTS)
tree = app_commands.CommandTree(bot)

# ---- DB init ----
Base.metadata.create_all(bind=engine)

# ---- Helpers ----

def get_or_create_user(session: Session, discord_user_id: int) -> User:
    user = session.get(User, discord_user_id)
    if user is None:
        user = User(id=discord_user_id, opted_in=True)
        session.add(user)
        session.commit()
    return user

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
        await tree.sync(guild=guild)
        print(f"Commands synced to guild {GUILD_ID}")
    else:
        await tree.sync()
        print("Global command sync initiated (may take time).")
    print(f"Logged in as {bot.user}")

@bot.event
async def on_message(message: discord.Message):
    try:
        if message.author.bot:
            return

        with SessionLocal() as session:
            # Only log from allowed channels
            if not await ensure_channel_allowed(session, message.channel.id):
                return
            user = get_or_create_user(session, message.author.id)

            # Store minimal message features
            links = extract_links(message.content or "")
            images = int(any(a.content_type and a.content_type.startswith("image/") for a in message.attachments))
            emojis = emoji_density(message.content or "")
            reactions = sum([r.count for r in message.reactions]) if message.reactions else 0

            m = Message(
                user_id=user.id,
                channel_id=message.channel.id,
                created_at=message.created_at or datetime.utcnow(),
                text=message.content or "",
                links=links,
                emojis=emojis,
                images=images,
                reactions=reactions
            )
            session.add(m)
            user.last_seen_at = datetime.utcnow()
            session.commit()
            
            # Analyze message with ChatGPT and send response
            if message.content and len(message.content.strip()) >= 3:  # Only analyze substantial messages
                try:
                    score_adjustment = analyze_message_with_chatgpt(message.content, message.author.display_name)
                    
                    # Create response based on ChatGPT analysis
                    if score_adjustment == 1:
                        response_text = "🎭 **PERFORMATIVE** - This message shows performative male culture vibes"
                        color = 0xff6b6b  # Red for performative
                    elif score_adjustment == -1:
                        response_text = "💪 **NON-PERFORMATIVE** - This message shows toxically masculine vibes"
                        color = 0x4ecdc4  # Teal for non-performative
                    else:
                        response_text = "😐 **NEUTRAL** - This message is neither performative nor non-performative"
                        color = 0x95a5a6  # Gray for neutral
                    
                    # Create embed
                    embed = discord.Embed(
                        title="Perform-o-Meter Analysis",
                        description=response_text,
                        color=color
                    )
                    embed.set_footer(text=f"Analyzed message from {message.author.display_name}")
                    
                    # Send the analysis
                    await message.channel.send(embed=embed)
                    
                except Exception as chatgpt_error:
                    print(f"ChatGPT analysis error: {chatgpt_error}")
                    # Don't send anything if ChatGPT fails to avoid spam
                    
    except Exception as e:
        print("on_message error:", e)

# ---- Commands ----

@tree.command(name="optin", description="Opt in to Perform-o-Meter (no longer required - all users are automatically included)")
async def optin(interaction: discord.Interaction):
    with SessionLocal() as session:
        user = get_or_create_user(session, interaction.user.id)
        user.opted_in = True
        session.commit()
    await interaction.response.send_message("You're already included! All users are automatically analyzed. Use `/optout` if you want to exclude yourself.", ephemeral=True)

@tree.command(name="optout", description="Opt out of Perform-o-Meter")
async def optout(interaction: discord.Interaction):
    with SessionLocal() as session:
        user = get_or_create_user(session, interaction.user.id)
        user.opted_in = False
        session.commit()
    await interaction.response.send_message("Opted out. I've stopped analyzing your messages.", ephemeral=True)

@tree.command(name="allow_channel", description="Allow scoring in this channel (admin)")
@app_commands.checks.has_permissions(manage_guild=True)
async def allow_channel(interaction: discord.Interaction):
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
@app_commands.describe(member="User to score", days="Window in days (1-60)")
async def meter(interaction: discord.Interaction, member: discord.Member, days: app_commands.Range[int,1,60]=14):
    with SessionLocal() as session:
        score, info = compute_user_score_chatgpt(session, member.id, days=days)
    
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
    
    # Add examples
    examples = "\n".join([f"• {e}" for e in info.get("examples", [])]) or "—"
    embed.add_field(name="Message Examples", value=examples, inline=False)
    
    await interaction.response.send_message(embed=embed)

@tree.command(name="leaderboard", description="Top performative-ness (all users)")
@app_commands.describe(days="Window in days (1-60)")
async def leaderboard(interaction: discord.Interaction, days: app_commands.Range[int,1,60]=14):
    # Compute on-demand for all guild members, but only include those with existing data
    await interaction.response.defer()
    guild = interaction.guild
    with SessionLocal() as session:
        rows = []
        for m in guild.members:
            if m.bot: 
                continue
            # Only include users who already exist in the database (have been analyzed)
            user = session.get(User, m.id)
            if user:
                score, _ = compute_user_score_chatgpt(session, m.id, days=days)
                rows.append((m.display_name, score))

    rows.sort(key=lambda x: x[1], reverse=True)
    lines = [f"**{i+1}.** {name} — **{score}**" for i,(name,score) in enumerate(rows[:15])]
    msg = "\n".join(lines) or "No activity yet. Start chatting to get scored!"
    await interaction.followup.send(f"**Leaderboard (last {days}d)**\n{msg}")

@tree.command(name="why", description="Explain a user's score")
@app_commands.describe(member="User to explain", days="Window in days (1-60)")
async def why(interaction: discord.Interaction, member: discord.Member, days: app_commands.Range[int,1,60]=14):
    with SessionLocal() as session:
        score, info = compute_user_score_chatgpt(session, member.id, days=days)
    
    # Create detailed explanation with ChatGPT analysis
    text = f"**{member.display_name} — {score}/100 (last {days}d)**\n\n"
    text += f"**ChatGPT Analysis:**\n"
    text += f"• Total Messages: {info.get('total_messages', 0)}\n"
    text += f"• Performative: {info.get('performative_messages', 0)}\n"
    text += f"• Non-Performative: {info.get('non_performative_messages', 0)}\n"
    text += f"• Neutral: {info.get('neutral_messages', 0)}\n"
    text += f"• Raw Score: {info.get('raw_score', 0)}\n\n"
    
    examples = "\n".join([f"• {e}" for e in info.get("examples", [])]) or "—"
    text += f"**Message Examples:**\n{examples}"
    
    await interaction.response.send_message(text)

# ---- Config commands ----

@tree.command(name="config_show", description="Show current scoring config")
async def config_show(interaction: discord.Interaction):
    with SessionLocal() as session:
        cfg = get_config(session)
    pretty = json.dumps(cfg, indent=2, ensure_ascii=False)
    await interaction.response.send_message(f"```json\n{pretty}\n```", ephemeral=True)

@tree.command(name="config_set_weight", description="Set weight for a category")
@app_commands.describe(category="One of: aesthetic, text_vibe, links_media, self_presentation, engagement, sincerity",
                       value="0.0 to 1.0 (weights need not sum to 1)")
@app_commands.checks.has_permissions(manage_guild=True)
async def config_set_weight(interaction: discord.Interaction, category: str, value: app_commands.Range[float, 0.0, 1.0]):
    with SessionLocal() as session:
        cfg = get_config(session)
        weights = cfg.get("weights", {})
        if category not in weights:
            await interaction.response.send_message(f"Unknown category '{category}'.", ephemeral=True)
            return
        weights[category] = float(value)
        set_config_key("weights", weights, session)
    await interaction.response.send_message(f"Updated `{category}` weight to {value}.", ephemeral=True)

@tree.command(name="config_tokens_add", description="Add a token to a group")
@app_commands.describe(group="e.g., beverages, books, aesthetic, accessories, music", token="The word/phrase to add")
@app_commands.checks.has_permissions(manage_guild=True)
async def config_tokens_add(interaction: discord.Interaction, group: str, token: str):
    with SessionLocal() as session:
        cfg = get_config(session)
        tokens = cfg.get("tokens", {})
        lst = tokens.get(group, [])
        if token in lst:
            await interaction.response.send_message("Token already present.", ephemeral=True)
            return
        lst.append(token)
        tokens[group] = lst
        set_config_key("tokens", tokens, session)
    await interaction.response.send_message(f"Added token '{token}' to '{group}'.", ephemeral=True)

@tree.command(name="config_tokens_remove", description="Remove a token from a group")
@app_commands.describe(group="e.g., beverages, books, aesthetic, accessories, music", token="The word/phrase to remove")
@app_commands.checks.has_permissions(manage_guild=True)
async def config_tokens_remove(interaction: discord.Interaction, group: str, token: str):
    with SessionLocal() as session:
        cfg = get_config(session)
        tokens = cfg.get("tokens", {})
        lst = tokens.get(group, [])
        if token not in lst:
            await interaction.response.send_message("Token not found.", ephemeral=True)
            return
        lst = [t for t in lst if t != token]
        tokens[group] = lst
        set_config_key("tokens", tokens, session)
    await interaction.response.send_message(f"Removed token '{token}' from '{group}'.", ephemeral=True)

# ---- Entrypoint ----
if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("DISCORD_BOT_TOKEN missing. Put it in .env or env vars.")
    # Run!
    bot.run(TOKEN)
