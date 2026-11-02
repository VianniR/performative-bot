from __future__ import annotations
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Float, JSON, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
from .db import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)  # discord user id (snowflake fits into int64)
    username = Column(String, nullable=True)  # Discord username for easy lookup
    opted_in = Column(Boolean, default=False, nullable=False)
    consented_at = Column(DateTime, nullable=True)  # Fresh explicit consent; legacy flags are insufficient.
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_seen_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    messages = relationship("Message", back_populates="user", cascade="all, delete-orphan")

class ChannelConfig(Base):
    __tablename__ = "channels"
    channel_id = Column(Integer, primary_key=True, index=True)  # discord channel id
    allowed = Column(Boolean, default=False, nullable=False)

class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    channel_id = Column(Integer, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    text = Column(String, default="", nullable=False)
    links = Column(JSON, nullable=True)
    emojis = Column(Float, default=0.0, nullable=False)
    images = Column(Integer, default=0, nullable=False)
    reactions = Column(Integer, default=0, nullable=False)

    user = relationship("User", back_populates="messages")

class ConfigKV(Base):
    __tablename__ = "config"
    key = Column(String, primary_key=True)
    value = Column(JSON, nullable=False)

class Score(Base):
    __tablename__ = "scores"
    user_id = Column(Integer, primary_key=True)
    window_days = Column(Integer, primary_key=True)
    score = Column(Float, default=0.0, nullable=False)
    breakdown = Column(JSON, nullable=False, default=dict)
