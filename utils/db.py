"""PostgreSQL 連線管理（SQLAlchemy sync engine，搭配 asyncio.to_thread 使用）。"""
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

load_dotenv(override=False)

DATABASE_URL = os.getenv("SYNC_DATABASE_URL") or os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL, pool_size=5, max_overflow=10, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass
