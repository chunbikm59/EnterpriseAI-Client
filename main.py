from fastapi import FastAPI
import uvicorn
from chainlit.utils import mount_chainlit
import contextlib
from mcp_servers import (
    weather,
    user_custom_prompt
)
# Create a combined lifespan to manage both session managers
@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    async with contextlib.AsyncExitStack() as stack:
        await stack.enter_async_context(weather.mcp.session_manager.run())
        await stack.enter_async_context(user_custom_prompt.mcp.session_manager.run())
        yield


app = FastAPI(lifespan=lifespan)
app.mount("/mcp-weather", weather.mcp.streamable_http_app())
app.mount("/mcp-user-custom-prompt", user_custom_prompt.mcp.streamable_http_app())
mount_chainlit(app=app, target="ui/chat.py", path="/")

if __name__ == '__main__':
    uvicorn.run(app=app, host='0.0.0.0', port=8000)