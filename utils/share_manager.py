import uuid

from sqlalchemy.exc import IntegrityError

from utils.db import SessionLocal
from utils.models import SharedThread


def get_or_create_share_token(thread_id: str, user_id: str, conversation_folder: str) -> str:
    """取得或建立分享 token（冪等：同一 thread_id 永遠回傳同一 token）。"""
    with SessionLocal() as session:
        existing = (
            session.query(SharedThread)
            .filter(SharedThread.thread_id == thread_id)
            .first()
        )
        if existing:
            return existing.token

        token = uuid.uuid4().hex
        record = SharedThread(
            token=token,
            thread_id=thread_id,
            user_id=user_id,
            conversation_folder=conversation_folder,
        )
        session.add(record)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            existing = (
                session.query(SharedThread)
                .filter(SharedThread.thread_id == thread_id)
                .one()
            )
            return existing.token

        return token


def get_shared_thread_record(token: str) -> "SharedThread | None":
    """給 token 回傳 SharedThread ORM 物件。格式錯誤或不存在回傳 None。

    使用 expunge() 讓物件脫離 session，避免 DetachedInstanceError。
    """
    if not token or len(token) != 32 or not all(c in "0123456789abcdef" for c in token):
        return None
    with SessionLocal() as session:
        record = (
            session.query(SharedThread)
            .filter(SharedThread.token == token)
            .first()
        )
        if record is not None:
            session.expunge(record)
        return record
