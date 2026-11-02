from __future__ import annotations
import re, os
from collections import Counter
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from sqlalchemy.orm import Session
from .models import Message, User, ChannelConfig
from .config import get_config

try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    print("Warning: OpenAI not available. Install with: pip install openai")

def time_decay(days: float, half_life: float) -> float:
    return 0.5 ** (days / max(half_life, 0.1))

def extract_links(text: str) -> List[str]:
    return re.findall(r'https?://\S+', text or "")

def emoji_density(text: str) -> float:
    # naive approximation: characters beyond BMP planes likely emojis (not perfect)
    if not text: return 0.0
    count = sum(1 for ch in text if ord(ch) >= 0x1F000)
    return count / max(len(text), 1)

def _token_hits(text: str, tokens: List[str]) -> int:
    hits = 0
    for t in tokens:
        pat = r'\b' + re.escape(t) + r'\b'
        hits += len(re.findall(pat, text, flags=re.IGNORECASE))
    return hits

def eligible_messages(session: Session, user_id: int, days: int, channel_ids):
    """Fail closed: explicit consent, post-consent content, visible allowed channels."""
    if not 1 <= days <= 60:
        raise ValueError("days must be between 1 and 60")
    user = session.get(User, user_id)
    if not user or not user.opted_in or user.consented_at is None or not channel_ids:
        return []
    start = max(datetime.utcnow() - timedelta(days=days), user.consented_at)
    return (session.query(Message)
            .filter(Message.user_id == user_id, Message.created_at >= start,
                    Message.channel_id.in_(channel_ids),
                    Message.channel_id.in_(session.query(ChannelConfig.channel_id).filter_by(allowed=True)))
            .order_by(Message.created_at.desc(), Message.id.desc()).all())


def compute_user_score(session: Session, user_id: int, days: int = 14, *, channel_ids=(), guild_id=None) -> Tuple[float, Dict]:
    cfg = get_config(session, guild_id=guild_id)
    weights = cfg.get("weights", {})
    tokens_cfg = cfg.get("tokens", {})
    half = cfg.get("decay", {}).get("half_life_days", 7)

    now = datetime.utcnow()
    msgs = eligible_messages(session, user_id, days, channel_ids)
    if not msgs:
        return 0.0, {"examples": []}

    text_tokens: List[str] = []
    for group in ("aesthetic", "beverages", "books", "music", "accessories"):
        text_tokens.extend(tokens_cfg.get(group, []))

    total_weight = 0.0
    total_hits = 0.0
    link_domains: Counter = Counter()
    imgs = 0.0
    reacts = 0.0
    lengths: List[int] = []
    examples: List[str] = []

    for m in msgs:
        age_days = (now - m.created_at).total_seconds() / 86400.0
        w = time_decay(age_days, half)
        total_weight += w

        hits = _token_hits(m.text or "", text_tokens)
        total_hits += hits * w

        for L in (m.links or []):
            dom = re.sub(r'^https?://(www\.)?', '', L).split('/')[0]
            link_domains[dom] += w

        imgs += int(m.images) * w
        reacts += int(m.reactions) * w
        lengths.append(len(m.text or ""))

    text_vibe = min(1.0, (total_hits / max(total_weight, 1)) / 3.0)
    links_media = min(1.0, (link_domains["open.spotify.com"] + link_domains["goodreads.com"] + link_domains["letterboxd.com"]) / max(total_weight, 1))
    self_presentation = min(1.0, imgs / max(total_weight, 1) / 1.5)
    engagement = min(1.0, reacts / max(total_weight, 1) / 2.0)
    avg_len = (sum(lengths) / len(lengths)) if lengths else 0.0
    sincerity = min(1.0, (avg_len / 180.0))

    # aesthetic currently 0 unless we later parse nick/bio; kept for config completeness
    aesthetic = 0.0

    breakdown = {
        "text_vibe": round(text_vibe, 3),
        "links_media": round(links_media, 3),
        "self_presentation": round(self_presentation, 3),
        "engagement": round(engagement, 3),
        "sincerity": round(sincerity, 3),
        "aesthetic": round(aesthetic, 3),
        "examples": examples,
        "top_domains": dict(link_domains.most_common(5)),
    }

    score = 100.0 * (
        weights.get("text_vibe", 0)*text_vibe +
        weights.get("links_media", 0)*links_media +
        weights.get("self_presentation", 0)*self_presentation +
        weights.get("engagement", 0)*engagement +
        weights.get("sincerity", 0)*sincerity +
        weights.get("aesthetic", 0)*aesthetic
    )
    return round(max(0, min(100, score)), 1), breakdown

def analyze_message_with_chatgpt(message_text: str, user_display_name: str = "") -> int | None:
    """
    Analyze a message with ChatGPT and return a score adjustment.
    Returns: +1 (performative), 0 (neutral), or -1 (non-performative).
    """
    if not OPENAI_AVAILABLE or not os.getenv("OPENAI_API_KEY"):
        return None

    # Quick heuristic check for fraternities to ensure consistency
    text_lower = message_text.lower()
    if any(word in text_lower for word in ['frat', 'fraternity', 'sorority', 'greek life']):
        return -1  # Always NON-PERFORMATIVE for fraternities

    client = None
    try:
        client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"), timeout=15.0, max_retries=0)

        prompt = f"""
Analyze this Discord message for "performative male" culture vs "toxic masculinity":

Message: "{message_text}"

PERFORMATIVE indicators (respond with "PERFORMATIVE"):
- Aesthetic lifestyle content (matcha, oat milk, cozy vibes)
- Name-dropping trendy things (Clairo, Boygenius, Sally Rooney, Murakami)
- Soft/emotional language ("in my feels", "soft launch", "main character energy")
- Curated self-presentation (photo dumps, aesthetic posts)
- Trying to appear cultured/trendy (book recommendations, music taste)
- "That girl" energy but for men

NON-PERFORMATIVE indicators (respond with "NON-PERFORMATIVE"):
- Dark/edgy humor
- Misogynistic language or attitudes
- Homophobic or transphobic content
- Arrogant/alpha male behavior
- Toxic masculinity traits
- "Sigma male" or "red pill" content
- Dismissive of emotions or vulnerability
- Fraternities and sororities (frat, sorority, Greek life, fraternity)
- Stereotypically male attitudes

NEUTRAL (respond with "NEUTRAL"):
- Normal conversation
- Questions or answers
- Basic information sharing
- Neither performative nor toxic

Be decisive - most messages should be classified as either PERFORMATIVE or NON-PERFORMATIVE, not neutral.

Respond with only: PERFORMATIVE, NON-PERFORMATIVE, or NEUTRAL
"""

        response = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=10,
            temperature=0.7,
            store=False
        )

        result = response.choices[0].message.content.strip().upper()

        if result == "PERFORMATIVE":
            return 1
        elif result == "NON-PERFORMATIVE":
            return -1
        else:  # NEUTRAL or any other response
            return 0

    except Exception:
        # Exception bodies may contain request content or credentials.
        return None  # Signal unavailable so caller can inform user
    finally:
        if client is not None:
            client.close()

def compute_user_score_chatgpt(session: Session, user_id: int, days: int = 14, *, channel_ids=(), guild_id=None) -> Tuple[float, Dict]:
    """
    Compute user score using ChatGPT analysis instead of heuristics.
    """
    msgs = eligible_messages(session, user_id, days, channel_ids)
    if not msgs:
        return 0.0, {"total_messages": 0, "chatgpt_analysis": "No eligible messages"}

    total_score = 0
    performative_count = 0
    non_performative_count = 0
    neutral_count = 0
    examples = []

    # Analyze most recent messages consistently (last 10 messages)
    messages_to_analyze = msgs[:10]

    for m in messages_to_analyze:
        if not m.text or len(m.text.strip()) < 3:  # Skip very short messages
            continue

        # Analyze with ChatGPT (skip if unavailable)
        score_adjustment = analyze_message_with_chatgpt(m.text)
        if score_adjustment is None:
            continue
        total_score += score_adjustment

        # Track categories
        if score_adjustment == 1:
            performative_count += 1
        elif score_adjustment == -1:
            non_performative_count += 1
        else:
            neutral_count += 1


    # Convert to 0-100 scale with more reasonable scaling
    # Base score of 50, then adjust based on ChatGPT analysis (less aggressive)
    final_score = max(0, min(100, 50 + (total_score * 1.5)))

    analyzed = performative_count + non_performative_count + neutral_count
    breakdown = {
        "total_messages": len(msgs),
        "performative_messages": performative_count,
        "non_performative_messages": non_performative_count,
        "neutral_messages": neutral_count,
        "raw_score": total_score,
        "examples": examples,
        "chatgpt_analysis": f"Analyzed {analyzed} of {len(messages_to_analyze)} sampled messages",
        "latest_message_id": msgs[0].id if msgs else None
    }

    # Legacy cache lacks channel/consent scope and expiry; never read or overwrite it.
    if not analyzed:
        fallback, details = compute_user_score(session, user_id, days, channel_ids=channel_ids, guild_id=guild_id)
        details.update(breakdown)
        details["chatgpt_analysis"] = "LLM unavailable or no substantial text; heuristic fallback"
        return fallback, details
    return round(final_score, 1), breakdown
