"""Conversation DB CRUD（同步，搭配 asyncio.to_thread 使用）。"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError

from utils.db import SessionLocal
from utils.models import Conversation


def create_conversation(user_id: str, conversation_id: str) -> None:
    """在 DB 建立新對話記錄。若已存在則略過。"""
    conv_uuid = uuid.UUID(conversation_id)
    with SessionLocal() as session:
        existing = session.get(Conversation, conv_uuid)
        if existing:
            return
        conv = Conversation(
            id=conv_uuid,
            user_id=user_id,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(conv)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()


def finalize_conversation(conversation_id: str, message_count: int) -> None:
    """標記對話結束，更新 ended_at 與 message_count。"""
    conv_uuid = uuid.UUID(conversation_id)
    with SessionLocal() as session:
        conv = session.get(Conversation, conv_uuid)
        if conv:
            conv.ended_at = datetime.now(timezone.utc)
            conv.updated_at = datetime.now(timezone.utc)
            conv.message_count = message_count
            session.commit()


def update_conversation_title(conversation_id: str, title: str) -> None:
    """更新對話標題。"""
    conv_uuid = uuid.UUID(conversation_id)
    with SessionLocal() as session:
        conv = session.get(Conversation, conv_uuid)
        if conv:
            conv.title = title
            conv.updated_at = datetime.now(timezone.utc)
            session.commit()


def list_conversations(user_id: str, offset: int = 0, limit: int = 10,
                       search: Optional[str] = None) -> dict:
    """列出使用者的對話摘要（依 updated_at 降序）。"""
    with SessionLocal() as session:
        base_q = select(Conversation).where(Conversation.user_id == user_id)
        count_q = select(func.count()).where(Conversation.user_id == user_id)
        if search:
            pattern = f"%{search}%"
            base_q = base_q.where(Conversation.title.ilike(pattern))
            count_q = count_q.where(Conversation.title.ilike(pattern))

        total = session.execute(count_q).scalar() or 0

        rows = session.execute(
            base_q
            .order_by(Conversation.updated_at.desc())
            .offset(offset)
            .limit(limit)
        ).scalars().all()

    results = [
        {
            "conversation_id": str(r.id),
            "title": r.title,
            "created_at": r.created_at.isoformat() if r.created_at else "",
            "updated_at": r.updated_at.isoformat() if r.updated_at else "",
            "ended_at": r.ended_at.isoformat() if r.ended_at else None,
            "message_count": r.message_count,
        }
        for r in rows
    ]

    return {
        "conversations": results,
        "total": total,
        "offset": offset,
        "limit": limit,
        "has_more": (offset + limit) < total,
    }
