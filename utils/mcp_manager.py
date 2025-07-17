from typing import Dict, Any, List, Optional
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client
import asyncio
from types import FunctionType
from contextlib import AsyncExitStack

# MCP 連線管理
class MCPConnectionManager:
    def __init__(self, config=None, on_connect:FunctionType=None):
        self.connections = {}  # 儲存每個連線的 context manager
        self.sessions = {}
        self.tools = {}        
        self.config = config or {}
        self.on_connect = on_connect
        self.connection_tasks = {}  # 儲存每個連線的 task
        self.shutdown_event = asyncio.Event()
        
    def connect_mcp_server(self, headers: Optional[dict] = None):
        """初始化所有已啟用的 MCP 伺服器連線"""
        for mcp_name, config in self.config.items():
            if config.get('enabled', False):
                self.add_connection(mcp_name, config, headers)

    async def add_connection(self, mcp_name: str, config: dict, headers: Optional[dict] = None):
        """動態新增一個 MCP 連線"""
        if mcp_name in self.connection_tasks:
            # 如果已經存在，先移除舊的連線
            await self.remove_connection(mcp_name)
        
        # 創建新的連線 task
        task = asyncio.create_task(self._single_connection_task(mcp_name, config, headers))
        self.connection_tasks[mcp_name] = task
        
    async def remove_connection(self, mcp_name: str):
        """動態移除一個 MCP 連線"""
        if mcp_name in self.connection_tasks:
            # 取消 task
            task = self.connection_tasks[mcp_name]
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            
            # 清理相關資源
            del self.connection_tasks[mcp_name]
            if mcp_name in self.sessions:
                del self.sessions[mcp_name]
            if mcp_name in self.tools:
                del self.tools[mcp_name]
            if mcp_name in self.connections:
                del self.connections[mcp_name]
                
            # 給 HTTP 連線一些時間來正確關閉
            await asyncio.sleep(0.1)
                
    async def _single_connection_task(self, mcp_name: str, config: dict, headers: dict):
        """為單一 MCP 伺服器建立連線的 task"""
        streams_context = None
        session_context = None
        
        try:
            async with AsyncExitStack() as stack:
                if config['type'] == 'http':
                    streams_context = streamablehttp_client(
                        url=config['url'],
                        headers=headers
                    )        
                    read_stream, write_stream, _ = await stack.enter_async_context(streams_context)
                elif config['type'] == 'stdio':
                    # stdio 
                    server_params = StdioServerParameters(
                        command=config['command'],
                        args=config.get('args'),
                        env=config.get('env')
                    )
                    streams_context = stdio_client(server_params)
                    read_stream, write_stream = await stack.enter_async_context(streams_context)
                else:
                    return
                
                # 建立 session
                session_context = ClientSession(read_stream, write_stream)
                session = await stack.enter_async_context(session_context)
                await session.initialize()
                
                # 儲存 session 和工具
                self.sessions[mcp_name] = session
                tools = await self.get_tools_from_session(mcp_name)
                self.tools[mcp_name] = tools
                
                # 呼叫回調函數
                if self.on_connect:
                    await self.on_connect(mcp_name, tools)
                
                # 等待直到被取消或關閉
                await self.shutdown_event.wait()
                
        except asyncio.CancelledError:
            # 正常的取消，清理資源
            if mcp_name in self.sessions:
                del self.sessions[mcp_name]
            if mcp_name in self.tools:
                del self.tools[mcp_name]
            raise
        except Exception as e:
            print(f"MCP 伺服器 {mcp_name} 連線錯誤: {str(e)}")
            # 清理資源
            if mcp_name in self.sessions:
                del self.sessions[mcp_name]
            if mcp_name in self.tools:
                del self.tools[mcp_name]
        finally:
            # 確保資源被正確清理
            try:
                # 給一點時間讓 HTTP 連線正常關閉
                if config['type'] == 'http':
                    await asyncio.sleep(0.1)
            except:
                pass

    async def get_tools_from_session(self, name: str):
        """從 session 取得工具列表"""
        if name not in self.sessions:
            return []
        
        try:
            session = self.sessions[name]
            result = await session.list_tools()
            return [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.inputSchema,
                }
                for t in result.tools
            ]
        except Exception as e:
            print(f"從 {name} 取得工具列表時發生錯誤: {str(e)}")
            return []
    
    async def update_tools(self):
        """更新所有連線的工具列表"""
        for name in list(self.tools.keys()):
            if name in self.sessions:
                tools = await self.get_tools_from_session(name)
                self.tools[name] = tools

    async def call_tool(self, server_name: str, tool_name: str, arguments: dict):
        """呼叫指定 server 的工具"""
        if server_name not in self.sessions:
            raise Exception(f"MCP server {server_name} 未連線")
        
        session = self.sessions[server_name]
        return await session.call_tool(tool_name, arguments)
    
    async def shutdown(self):
        """關閉所有連線"""
        # 設置關閉事件
        self.shutdown_event.set()
        
        # 取消所有連線 tasks
        for mcp_name in list(self.connection_tasks.keys()):
            await self.remove_connection(mcp_name)
        
        # 清理所有資源
        self.sessions.clear()
        self.tools.clear()
        self.connections.clear()
        self.connection_tasks.clear()
    
    def get_connected_servers(self):
        """取得已連線的伺服器列表"""
        return list(self.sessions.keys())
    
    def is_connected(self, mcp_name: str):
        """檢查指定的 MCP 伺服器是否已連線"""
        return mcp_name in self.sessions and mcp_name in self.connection_tasks
    