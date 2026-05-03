import pathlib
import shutil
import uuid
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError

from utils.db import SessionLocal
from utils.models import PublishedArtifact

_PROJECT_ROOT = pathlib.Path(__file__).parent.parent
_PUBLISHED_DIR = _PROJECT_ROOT / "published"


def publish_artifact(
    artifact_id: str,
    title: str,
    user_id: str,
    html_path: str,
    html_content: str | None = None,
    conversation_folder: str | None = None,
) -> str:
    """將 artifact HTML 複製到公開目錄，回傳 token（重複發布回傳舊 token）。

    html_content 若提供，直接寫入；否則複製原始檔案。
    conversation_folder 儲存於 DB，供資源路由 serve 附屬檔案使用。
    """
    with SessionLocal() as session:
        existing = (
            session.query(PublishedArtifact)
            .filter(PublishedArtifact.artifact_id == artifact_id)
            .first()
        )
        if existing:
            if html_content is not None:
                dest = _PUBLISHED_DIR / existing.html_file
                dest.write_text(html_content, encoding="utf-8")
            if conversation_folder and not existing.conversation_folder:
                existing.conversation_folder = conversation_folder
                session.commit()
            return existing.token

        token = uuid.uuid4().hex
        _PUBLISHED_DIR.mkdir(parents=True, exist_ok=True)
        dest = _PUBLISHED_DIR / f"{token}.html"
        if html_content is not None:
            dest.write_text(html_content, encoding="utf-8")
        else:
            shutil.copy2(html_path, dest)

        record = PublishedArtifact(
            token=token,
            artifact_id=artifact_id,
            title=title,
            user_id=user_id,
            published_at=datetime.now(timezone.utc),
            html_file=f"{token}.html",
            conversation_folder=conversation_folder,
        )
        session.add(record)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            dest.unlink(missing_ok=True)
            existing = (
                session.query(PublishedArtifact)
                .filter(PublishedArtifact.artifact_id == artifact_id)
                .one()
            )
            return existing.token

        return token


def get_published_html_path(token: str) -> pathlib.Path | None:
    """給 token 回傳 published HTML 檔案的絕對路徑，不存在回傳 None。"""
    if not token or not all(c in "0123456789abcdef" for c in token) or len(token) != 32:
        return None
    path = _PUBLISHED_DIR / f"{token}.html"
    return path if path.is_file() else None


def get_published_artifact_record(token: str) -> "PublishedArtifact | None":
    """給 token 回傳 PublishedArtifact ORM 物件，不存在或格式錯誤回傳 None。

    使用 expunge() 讓物件脫離 session，避免 session 關閉後觸發 DetachedInstanceError。
    """
    if not token or len(token) != 32 or not all(c in "0123456789abcdef" for c in token):
        return None
    with SessionLocal() as session:
        record = (
            session.query(PublishedArtifact)
            .filter(PublishedArtifact.token == token)
            .first()
        )
        if record is not None:
            session.expunge(record)
        return record
