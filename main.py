import os
import logging
from fastapi import FastAPI, Request

logging.basicConfig(level=logging.WARNING)
logging.getLogger("chainlit_app").setLevel(logging.DEBUG)
logging.getLogger("utils").setLevel(logging.DEBUG)
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware
import uvicorn
from chainlit.utils import mount_chainlit
import contextlib
from routers import oauth

# buildin 已改為直接函數呼叫，不再需要 MCP HTTP server

@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(lifespan=lifespan)


@app.get("/api/config")
async def get_config():
    return JSONResponse({"enable_session_history": os.getenv("ENABLE_SESSION_HISTORY", "true").lower() in ("1", "true", "yes")})


# 添加 Session 中間件
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET_KEY", "your-secret-key-here"))

# 註冊路由器
app.include_router(oauth.router, prefix="/api/oauth", tags=["OAuth"])

mount_chainlit(app=app, target="chainlit_app/app.py", path="/")

if __name__ == '__main__':
    uvicorn.run(app='main:app', host='0.0.0.0', port=8000)
