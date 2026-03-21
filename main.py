import os
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware
import uvicorn
from chainlit.utils import mount_chainlit
import contextlib
from mcp_servers import (
    buildin
)
from routers import oauth

# buildin_app = buildin.mcp.http_app(path='/mcp')

# Create a combined lifespan to manage both session managers
@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    async with contextlib.AsyncExitStack() as stack:
        # 使用 AsyncExitStack 來管理多個 async context managers
        # await stack.enter_async_context(buildin_app.lifespan(app))
        await stack.enter_async_context(buildin.mcp.session_manager.run())
        yield


app = FastAPI(lifespan=lifespan)

# 限制 MCP endpoint 只允許本機連線
@app.middleware("http")
async def restrict_mcp_to_localhost(request: Request, call_next):
    if request.url.path.startswith("/mcp-buildin"):
        if request.client.host not in ("127.0.0.1", "::1"):
            return JSONResponse(status_code=403, content={"detail": "Forbidden"})
    return await call_next(request)

# 添加 Session 中間件
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET_KEY", "your-secret-key-here"))

# 註冊路由器
app.include_router(oauth.router, prefix="/api/oauth", tags=["OAuth"])

# app.mount("/mcp-buildin", buildin_app)
app.mount("/mcp-buildin", buildin.mcp.streamable_http_app())
mount_chainlit(app=app, target="chainlit_app/app.py", path="/")

if __name__ == '__main__':
    uvicorn.run(app='main:app', host='0.0.0.0', port=8000)
