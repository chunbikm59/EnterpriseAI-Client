import asyncio
import os
import shutil
import uuid

import chainlit as cl
from chainlit.data.chainlit_data_layer import ChainlitDataLayer
from chainlit.types import PaginatedResponse, PageInfo, ThreadFilter, Pagination, ThreadDict

from utils.db import SessionLocal
from utils.models import Conversation
from utils.conversation_manager import list_conversations, update_conversation_title
from chainlit_app.conversation_history import build_thread_steps_from_jsonl

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _build_chainlit_db_url() -> str | None:
    base = os.environ.get("SYNC_DATABASE_URL")
    if not base:
        return None
    url = base.replace("postgresql+psycopg2://", "postgresql://", 1)
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}options=-csearch_path%3Dchainlit"


_CHAINLIT_DB_URL = _build_chainlit_db_url()


class _JsonlDataLayer(ChainlitDataLayer):
    """覆寫 Chainlit Data Layer：
    - Step/Element 不寫 DB（UI 由 get_thread 從 JSONL 重建 steps/elements 並由框架推送）
    - list_threads / get_thread / delete_thread / update_thread 全部走 public.conversations
    - chainlit.Thread 完全不需要維護
    """

    # ── 不寫 Step / Element ──────────────────────────────────────
    async def create_step(self, step_dict): pass
    async def update_step(self, step_dict): pass
    async def delete_step(self, step_id): pass
    async def create_element(self, element): pass
    async def delete_element(self, element_id, thread_id=None): pass

    # ── ACL：從 public.conversations 查作者 ──────────────────────
    async def get_thread_author(self, thread_id: str) -> str:
        def _query():
            try:
                with SessionLocal() as session:
                    conv = session.get(Conversation, uuid.UUID(thread_id))
                    return conv.user_id if conv else None
            except Exception:
                return None

        return (await asyncio.to_thread(_query)) or ""

    # ── 側邊欄列表：從 public.conversations 讀 ───────────────────
    async def list_threads(
        self, pagination: Pagination, filters: ThreadFilter
    ) -> PaginatedResponse[ThreadDict]:
        identifier = None
        if filters.userId:
            rows = await self.execute_query(
                'SELECT identifier FROM "User" WHERE id = $1',
                {"id": filters.userId},
            )
            if rows:
                identifier = rows[0]["identifier"]
        if not identifier:
            return PaginatedResponse(
                pageInfo=PageInfo(hasNextPage=False, startCursor=None, endCursor=None),
                data=[],
            )

        limit = pagination.first or 10
        result = await asyncio.to_thread(
            list_conversations, identifier, 0, limit, filters.search
        )
        convs = result["conversations"]

        thread_dicts = [
            ThreadDict(
                id=c["conversation_id"],
                createdAt=c["created_at"],
                name=c["title"] or c["created_at"][:16].replace("T", " "),
                userId=filters.userId,
                userIdentifier=identifier,
                metadata={},
                steps=[],
                elements=[],
                tags=[],
            )
            for c in convs
        ]

        return PaginatedResponse(
            pageInfo=PageInfo(
                hasNextPage=result["has_more"],
                startCursor=thread_dicts[0]["id"] if thread_dicts else None,
                endCursor=thread_dicts[-1]["id"] if thread_dicts else None,
            ),
            data=thread_dicts,
        )

    # ── 重連恢復：從 public.conversations + JSONL 重建完整 ThreadDict ──
    async def get_thread(self, thread_id: str):
        def _get():
            try:
                with SessionLocal() as session:
                    conv = session.get(Conversation, uuid.UUID(thread_id))
                    if not conv:
                        return None
                    return {
                        "user_id": conv.user_id,
                        "title": conv.title,
                        "created_at": conv.created_at.isoformat() if conv.created_at else "",
                    }
            except Exception:
                return None

        conv_info = await asyncio.to_thread(_get)
        if not conv_info:
            return None

        identifier = conv_info["user_id"]
        rows = await self.execute_query(
            'SELECT id FROM "User" WHERE identifier = $1',
            {"identifier": identifier},
        )
        chainlit_user_id = str(rows[0]["id"]) if rows else None

        jsonl_path = os.path.join(
            _PROJECT_ROOT, "user_profiles", identifier, "conversations", thread_id, "history.jsonl"
        )
        steps, elements = await asyncio.to_thread(
            build_thread_steps_from_jsonl, jsonl_path, thread_id, identifier
        )

        return ThreadDict(
            id=thread_id,
            createdAt=conv_info["created_at"],
            name=conv_info.get("title") or conv_info["created_at"][:16].replace("T", " "),
            userId=chainlit_user_id,
            userIdentifier=identifier,
            metadata={},
            steps=steps,
            elements=elements,
            tags=[],
        )

    # ── 重命名：同步更新 public.conversations.title ───────────────
    async def update_thread(self, thread_id, name=None, user_id=None, metadata=None, tags=None):
        if name is not None:
            try:
                await asyncio.to_thread(update_conversation_title, thread_id, name)
            except Exception:
                pass

    # ── 刪除：同步刪 public.conversations + JSONL 目錄 ──────────
    async def delete_thread(self, thread_id: str):
        def _delete():
            with SessionLocal() as session:
                conv = session.get(Conversation, uuid.UUID(thread_id))
                if not conv:
                    return
                uid = conv.user_id
                session.delete(conv)
                session.commit()
            conv_dir = os.path.join(
                _PROJECT_ROOT, "user_profiles", uid, "conversations", thread_id
            )
            if os.path.isdir(conv_dir):
                shutil.rmtree(conv_dir)

        await asyncio.to_thread(_delete)


@cl.data_layer
def _get_data_layer():
    if not _CHAINLIT_DB_URL:
        return None
    return _JsonlDataLayer(database_url=_CHAINLIT_DB_URL, storage_client=None)
