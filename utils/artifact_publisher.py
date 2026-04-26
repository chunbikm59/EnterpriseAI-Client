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
) -> str:
    """將 artifact HTML 複製到公開目錄，回傳 token（重複發布回傳舊 token）。"""
    with SessionLocal() as session:
        existing = (
            session.query(PublishedArtifact)
            .filter(PublishedArtifact.artifact_id == artifact_id)
            .first()
        )
        if existing:
            return existing.token

        token = uuid.uuid4().hex
        _PUBLISHED_DIR.mkdir(parents=True, exist_ok=True)
        dest = _PUBLISHED_DIR / f"{token}.html"
        shutil.copy2(html_path, dest)

        record = PublishedArtifact(
            token=token,
            artifact_id=artifact_id,
            title=title,
            user_id=user_id,
            published_at=datetime.now(timezone.utc),
            html_file=f"{token}.html",
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
