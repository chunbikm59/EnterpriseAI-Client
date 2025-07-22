from typing import Dict, Any, List, Optional
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamablehttp_client
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
import asyncio
import json
import os
from pathlib import Path
from types import FunctionType
from contextlib import AsyncExitStack

# MCP 連線管理 - 使用 FastMCP 的寫法
class MCPConnectionManager:
    def __init__(self, id, config=None, on_connect:FunctionType=None, roots_config=None):
        self.id = id
        self.connections = {}  # 儲存每個連線的 context manager
        self.sessions = {}
        self.tools = {}        
        self.config = config or {}
        self.on_connect = on_connect
        self.connection_tasks = {}  # 儲存每個連線的 task
        self.shutdown_event = asyncio.Event()
        
        # Roots 功能支援
        self.roots_config = roots_config or {}
        self.available_roots = []  # 儲存可用的根目錄
        self.roots_capability = True  # 是否支援 roots 功能
        self._initialize_roots()
        
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
        """為單一 MCP 伺服器建立連線的 task - 使用 FastMCP 的寫法"""
        client = None
        roots=[f"file://{self.id}"]
        try:
            # 根據配置類型建立 FastMCP Client
            if config['transport'] == 'http':
                transport = StreamableHttpTransport(config['url'], headers={"header_test": "nice job"})
                # 使用 FastMCP Client 連接 HTTP 伺服器
                
                client = Client(transport, roots=roots)
                
            elif config['transport'] == 'stdio':
                # 使用 FastMCP Client 連接 stdio 伺服器
                # FastMCP 期望的配置格式
                stdio_config = {
                    "mcpServers": {
                        mcp_name: {
                            "command": config['command'],
                            "args": config.get('args', []),
                            "env": config.get('env', {}),
                            "cwd": config.get('cwd'),
                            "transport": "stdio"
                        }
                    }
                }
                client = Client(stdio_config, roots=roots)
            else:
                return
            
            # 使用 FastMCP Client 的 async context manager
            async with client:
                # 等待連線建立
                await client.ping()
                
                # 儲存 client session（FastMCP 的 session 屬性）
                self.sessions[mcp_name] = client.session
                
                # 取得工具列表
                tools = await self.get_tools_from_fastmcp_client(client)
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
            # 如果 FastMCP 連線失敗，嘗試回退到原始方法
            try:
                await self._fallback_connection_task(mcp_name, config, headers)
                return
            except Exception as fallback_error:
                print(f"回退連線方法也失敗: {str(fallback_error)}")
            
            # 清理資源
            if mcp_name in self.sessions:
                del self.sessions[mcp_name]
            if mcp_name in self.tools:
                del self.tools[mcp_name]
        finally:
            # 確保資源被正確清理
            try:
                # 給一點時間讓連線正常關閉
                await asyncio.sleep(0.1)
            except:
                pass

    async def _fallback_connection_task(self, mcp_name: str, config: dict, headers: dict):
        """回退到原始的連線方法"""
        streams_context = None
        session_context = None
        
        try:
            async with AsyncExitStack() as stack:
                if config['transport'] == 'http':
                    streams_context = streamablehttp_client(
                        url=config['url'],
                        headers=headers or {"roots": ['file:aaa']}
                    )        
                    read_stream, write_stream, _ = await stack.enter_async_context(streams_context)
                elif config['transport'] == 'stdio':
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
            print(f"MCP 伺服器 {mcp_name} 回退連線錯誤: {str(e)}")
            # 清理資源
            if mcp_name in self.sessions:
                del self.sessions[mcp_name]
            if mcp_name in self.tools:
                del self.tools[mcp_name]
        finally:
            # 確保資源被正確清理
            try:
                # 給一點時間讓 HTTP 連線正常關閉
                if config['transport'] == 'http':
                    await asyncio.sleep(0.1)
            except:
                pass

    async def get_tools_from_fastmcp_client(self, client: Client):
        """從 FastMCP client 取得工具列表"""
        try:
            tools_result = await client.list_tools()
            return [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.inputSchema,
                }
                for t in tools_result
            ]
        except Exception as e:
            print(f"從 FastMCP client 取得工具列表時發生錯誤: {str(e)}")
            return []

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
    
    # ===== Roots 功能支援 =====
    
    def _initialize_roots(self):
        """初始化根目錄配置"""
        try:
            # 從配置中載入根目錄
            if 'roots' in self.roots_config:
                for root_config in self.roots_config['roots']:
                    self._add_root_from_config(root_config)
            
            # 如果沒有配置，使用預設的當前工作目錄
            if not self.available_roots:
                current_dir = os.getcwd()
                self.available_roots.append({
                    "uri": f"file://{current_dir.replace(os.sep, '/')}",
                    "name": f"當前工作目錄 ({os.path.basename(current_dir)})"
                })
                
        except Exception as e:
            print(f"初始化根目錄時發生錯誤: {str(e)}")
            self.roots_capability = False
    
    def _add_root_from_config(self, root_config: dict):
        """從配置中加入根目錄"""
        try:
            path = root_config.get('path')
            name = root_config.get('name')
            
            if not path:
                return
            
            # 標準化路徑
            normalized_path = os.path.abspath(path)
            
            # 檢查路徑是否存在
            if not os.path.exists(normalized_path):
                print(f"警告: 根目錄路徑不存在: {normalized_path}")
                return
            
            # 轉換為 file:// URI
            uri = f"file://{normalized_path.replace(os.sep, '/')}"
            
            # 如果沒有提供名稱，使用目錄名稱
            if not name:
                name = os.path.basename(normalized_path) or normalized_path
            
            root = {
                "uri": uri,
                "name": name
            }
            
            # 避免重複加入
            if not any(r["uri"] == uri for r in self.available_roots):
                self.available_roots.append(root)
                
        except Exception as e:
            print(f"加入根目錄配置時發生錯誤: {str(e)}")
    
    def add_root(self, path: str, name: str = None) -> bool:
        """動態加入根目錄
        
        Args:
            path: 目錄路徑
            name: 顯示名稱（可選）
            
        Returns:
            bool: 是否成功加入
        """
        try:
            # 標準化路徑
            normalized_path = os.path.abspath(path)
            
            # 檢查路徑是否存在
            if not os.path.exists(normalized_path):
                print(f"錯誤: 路徑不存在: {normalized_path}")
                return False
            
            # 轉換為 file:// URI
            uri = f"file://{normalized_path.replace(os.sep, '/')}"
            
            # 如果沒有提供名稱，使用目錄名稱
            if not name:
                name = os.path.basename(normalized_path) or normalized_path
            
            root = {
                "uri": uri,
                "name": name
            }
            
            # 避免重複加入
            if any(r["uri"] == uri for r in self.available_roots):
                print(f"根目錄已存在: {uri}")
                return False
            
            self.available_roots.append(root)
            
            # 通知所有連線的伺服器根目錄列表已變更
            asyncio.create_task(self._notify_roots_changed())
            
            return True
            
        except Exception as e:
            print(f"加入根目錄時發生錯誤: {str(e)}")
            return False
    
    def remove_root(self, uri: str) -> bool:
        """移除根目錄
        
        Args:
            uri: 要移除的根目錄 URI
            
        Returns:
            bool: 是否成功移除
        """
        try:
            original_count = len(self.available_roots)
            self.available_roots = [r for r in self.available_roots if r["uri"] != uri]
            
            if len(self.available_roots) < original_count:
                # 通知所有連線的伺服器根目錄列表已變更
                asyncio.create_task(self._notify_roots_changed())
                return True
            
            return False
            
        except Exception as e:
            print(f"移除根目錄時發生錯誤: {str(e)}")
            return False
    
    def list_roots(self) -> List[Dict[str, str]]:
        """取得根目錄列表"""
        return self.available_roots.copy()
    
    async def _notify_roots_changed(self):
        """通知所有連線的伺服器根目錄列表已變更"""
        for session in self.sessions.values():
            try:
                # 發送根目錄列表變更通知
                await session.send_roots_list_changed()
            except Exception as e:
                print(f"發送根目錄變更通知時發生錯誤: {str(e)}")
