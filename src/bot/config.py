from __future__ import annotations
import os, yaml, json
from typing import Any, Dict
from .db import SessionLocal
from .models import ConfigKV

DEFAULT_CONFIG_PATH = os.getenv("CONFIG_PATH", "config.yaml")

def load_default_config() -> Dict[str, Any]:
    with open(DEFAULT_CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def get_config(session=None) -> Dict[str, Any]:
    close = False
    if session is None:
        session = SessionLocal(); close = True
    try:
        rows = {kv.key: kv.value for kv in session.query(ConfigKV).all()}
        base = load_default_config()
        # overlay DB values on top of file defaults
        for k,v in rows.items():
            base[k] = v
        return base
    finally:
        if close:
            session.close()

def set_config_key(key: str, value: Any, session=None) -> None:
    close = False
    if session is None:
        session = SessionLocal(); close = True
    try:
        row = session.get(ConfigKV, key)
        if row is None:
            row = ConfigKV(key=key, value=value)
            session.add(row)
        else:
            row.value = value
        session.commit()
    finally:
        if close:
            session.close()
