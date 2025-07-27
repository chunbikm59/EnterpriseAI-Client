from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from typing import Optional, Dict
import chainlit as cl
from chainlit.context import init_http_context, init_ws_context
from chainlit.session import WebsocketSession
import requests
import urllib
import secrets
import time
from datetime import datetime, timedelta

router = APIRouter()

# 儲存 access tokens 的簡單記憶體存儲（實際應用中應使用資料庫）
token_store: Dict[str, Dict] = {}

# Pydantic 模型
class TokenRequest(BaseModel):
    grant_type: str
    code: str
    redirect_uri: str
    client_id: Optional[str] = None
    client_secret: Optional[str] = None

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    refresh_token: Optional[str] = None

class UserInfo(BaseModel):
    id: str
    name: str
    email: str
    avatar_url: Optional[str] = None
    provider: str

@router.get("/mock-oauth-proveder")
async def auth_oauth_callback(request: Request, redirect_uri: str, state: str, code: Optional[str] = None):
    query = {"code": code or 'code'}
    query['provider_id'] = 'foobar'
    query['state'] = state
    redirect_url = f"{redirect_uri}?{urllib.parse.urlencode(query)}"

    return RedirectResponse(url=redirect_url, status_code=302)


@router.post("/token", response_model=TokenResponse)
async def get_access_token(token_request: TokenRequest):
    """
    交換 authorization code 為 access token
    """
    # 驗證 grant_type
    if token_request.grant_type != "authorization_code":
        raise HTTPException(
            status_code=400,
            detail="不支援的 grant_type，僅支援 'authorization_code'"
        )
    
    # 驗證 authorization code（這裡是模擬驗證）
    if not token_request.code:
        raise HTTPException(
            status_code=400,
            detail="缺少 authorization code"
        )
    
    # 生成 access token
    access_token = secrets.token_urlsafe(32)
    refresh_token = secrets.token_urlsafe(32)
    expires_in = 3600  # 1小時
    
    # 儲存 token 資訊
    token_info = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": datetime.now() + timedelta(seconds=expires_in),
        "code": token_request.code,
        "client_id": token_request.client_id,
        "user_id": f"user_{secrets.token_hex(8)}"  # 模擬用戶 ID
    }
    token_store[access_token] = token_info
    
    return TokenResponse(
        access_token=access_token,
        token_type="Bearer",
        expires_in=expires_in,
        refresh_token=refresh_token
    )


@router.get("/userinfo", response_model=UserInfo)
async def get_user_info(request: Request):
    """
    使用 access token 獲取使用者資訊
    """
    # 從 Authorization header 中提取 access token
    authorization = request.headers.get("Authorization")
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="缺少 Authorization header"
        )
    
    # 檢查 Bearer token 格式
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="無效的 Authorization header 格式，應為 'Bearer <token>'"
        )
    
    access_token = authorization[7:]  # 移除 "Bearer " 前綴
    
    # 驗證 access token
    token_info = token_store.get(access_token)
    if not token_info:
        raise HTTPException(
            status_code=401,
            detail="無效的 access token"
        )
    
    # 檢查 token 是否過期
    if datetime.now() > token_info["expires_at"]:
        # 清理過期的 token
        del token_store[access_token]
        raise HTTPException(
            status_code=401,
            detail="access token 已過期"
        )
    
    # 返回模擬的使用者資訊
    user_id = token_info["user_id"]
    return UserInfo(
        id=user_id,
        name=f"測試使用者 {user_id[-8:]}",
        email=f"{user_id}@example.com",
        avatar_url=f"https://api.dicebear.com/7.x/avataaars/svg?seed={user_id}",
        provider="foobar"
    )


@router.get("/token/validate")
async def validate_token(request: Request):
    """
    驗證 access token 的有效性
    """
    authorization = request.headers.get("Authorization")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="無效的 Authorization header"
        )
    
    access_token = authorization[7:]
    token_info = token_store.get(access_token)
    
    if not token_info:
        raise HTTPException(
            status_code=401,
            detail="無效的 access token"
        )
    
    if datetime.now() > token_info["expires_at"]:
        del token_store[access_token]
        raise HTTPException(
            status_code=401,
            detail="access token 已過期"
        )
    
    return {
        "valid": True,
        "expires_at": token_info["expires_at"].isoformat(),
        "user_id": token_info["user_id"]
    }


@router.delete("/token/revoke")
async def revoke_token(request: Request):
    """
    撤銷 access token
    """
    authorization = request.headers.get("Authorization")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="無效的 Authorization header"
        )
    
    access_token = authorization[7:]
    
    if access_token in token_store:
        del token_store[access_token]
        return {"message": "Token 已成功撤銷"}
    else:
        raise HTTPException(
            status_code=404,
            detail="Token 不存在或已被撤銷"
        )
