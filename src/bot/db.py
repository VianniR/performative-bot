from __future__ import annotations
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base

# Load configuration before constructing the engine. Importing never opens the DB.
load_dotenv()
DB_URL = os.getenv("DB_URL", "sqlite:///./performometer.db")
engine = create_engine(DB_URL, echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


def initialize_database(bind=engine):
    """Create missing tables and apply the two additive legacy user migrations.

    Run only at explicit startup, after the operator has backed up their DB.
    No records are updated, deleted, or reset. Legacy consent remains unverified.
    """
    from . import models  # register metadata

    with bind.begin() as connection:
        inspector = inspect(connection)
        if inspector.has_table("users"):
            columns = {column["name"] for column in inspector.get_columns("users")}
            for name, sql_type in (("username", "VARCHAR"), ("consented_at", "TIMESTAMP")):
                if name not in columns:
                    connection.execute(text(f"ALTER TABLE users ADD COLUMN {name} {sql_type}"))
        Base.metadata.create_all(bind=connection)
