from __future__ import annotations
import re, math
from collections import Counter
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from sqlalchemy import select
from sqlalchemy.orm import Session
from .models import Message
from .config import get_config

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

def compute_user_score(session: Session, user_id: int, days: int = 14) -> Tuple[float, Dict]:
    cfg = get_config(session)
    weights = cfg.get("weights", {})
    tokens_cfg = cfg.get("tokens", {})
    half = cfg.get("decay", {}).get("half_life_days", 7)

    now = datetime.utcnow()
    window_start = now - timedelta(days=days)

    msgs: List[Message] = (
        session.query(Message)
        .filter(Message.user_id == user_id, Message.created_at >= window_start)
        .order_by(Message.created_at.desc())
        .all()
    )
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
        if hits > 0 and len(examples) < 5:
            examples.append((m.text or "")[:160])

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
    return round(score, 1), breakdown
