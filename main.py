from fastapi import FastAPI
import uvicorn
from chainlit.utils import mount_chainlit
import contextlib
from routers import chainlit as chainlit_router
from mcp_servers import (
    buildin
)
buildin_app = buildin.mcp.http_app(path='/mcp')
# Create a combined lifespan to manage both session managers
@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    async with contextlib.AsyncExitStack() as stack:
        # 使用 AsyncExitStack 來管理多個 async context managers
        await stack.enter_async_context(buildin_app.lifespan(app))
        yield


app = FastAPI(lifespan=lifespan)
app.include_router(chainlit_router.router, prefix="/chainlit", tags=["Chainlit"])
app.mount("/mcp-buildin", buildin_app)
mount_chainlit(app=app, target="ui/chat.py", path="/")

if __name__ == '__main__':
    uvicorn.run(app=app, host='0.0.0.0', port=8000)
