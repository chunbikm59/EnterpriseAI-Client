from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware
import uvicorn
from chainlit.utils import mount_chainlit
import contextlib
from mcp_servers import (
    buildin
)
from routers import oauth

buildin_app = buildin.mcp.http_app(path='/mcp')

# Create a combined lifespan to manage both session managers
@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    async with contextlib.AsyncExitStack() as stack:
        # 使用 AsyncExitStack 來管理多個 async context managers
        await stack.enter_async_context(buildin_app.lifespan(app))
        yield


app = FastAPI(lifespan=lifespan)

# 添加 Session 中間件
app.add_middleware(SessionMiddleware, secret_key="your-secret-key-here")

# 註冊路由器
app.include_router(oauth.router, prefix="/api/oauth", tags=["OAuth"])

app.mount("/mcp-buildin", buildin_app)
mount_chainlit(app=app, target="chainlit_app/app.py", path="/")

if __name__ == '__main__':
    uvicorn.run(app='main:app', host='0.0.0.0', port=8000)
