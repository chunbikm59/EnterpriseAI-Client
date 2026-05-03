import os
import pathlib
import logging
import contextlib

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.sessions import SessionMiddleware
import uvicorn
from chainlit.utils import mount_chainlit
from routers import oauth
from routers import debug_chat
from routers import user_files
from routers import published
from routers import pptx_preview
from routers import memory
from routers import artifact_preview

logging.basicConfig(level=logging.WARNING, force=True)
logging.getLogger("chainlit_app").setLevel(logging.DEBUG)
logging.getLogger("utils").setLevel(logging.DEBUG)

_PROJECT_ROOT = pathlib.Path(__file__).parent
_UPLOADS_DIR = _PROJECT_ROOT / "chainlit_uploads"


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET_KEY", "your-secret-key-here"))
app.include_router(oauth.router, prefix="/api/oauth", tags=["OAuth"])
app.include_router(debug_chat.router, prefix="/api/debug", tags=["Debug"])
app.include_router(user_files.router, prefix="/api/user-files", tags=["User Files"])
app.include_router(published.router, tags=["Published"])
app.include_router(pptx_preview.router, tags=["PPTX Preview"])
app.include_router(memory.router, prefix="/api/memory", tags=["Memory"])
app.include_router(artifact_preview.router, tags=["Artifact Preview"])


@app.get("/api/config")
async def get_config():
    return JSONResponse({"enable_session_history": os.getenv("ENABLE_SESSION_HISTORY", "true").lower() in ("1", "true", "yes")})


@app.get("/api/uploads/{path:path}")
async def serve_upload(path: str):
    file_path = (_UPLOADS_DIR / path).resolve()
    try:
        file_path.relative_to(_UPLOADS_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=403)
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(file_path)


mount_chainlit(app=app, target="chainlit_app/app.py", path="/")

if __name__ == '__main__':
    uvicorn.run(app='main:app', host='0.0.0.0', port=8000)
