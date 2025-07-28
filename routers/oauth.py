from fastapi import APIRouter, Request, HTTPException, Depends, Form, Query
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordBearer, HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Union, Any
import chainlit as cl
from chainlit.context import init_http_context, init_ws_context
from chainlit.session import WebsocketSession
import requests
import urllib.parse
import secrets
import time
import hashlib
import base64
import json
import jwt
import os
from datetime import datetime, timedelta
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
import uuid

router = APIRouter()

# JWT 密鑰生成（實際應用中應從環境變數或安全存儲中獲取）
JWT_SECRET_KEY = secrets.token_urlsafe(64)
JWT_ALGORITHM = "HS256"

# RSA 密鑰對生成（用於 JWT 簽名）
private_key = rsa.generate_private_key(
    public_exponent=65537,
    key_size=2048,
    backend=default_backend()
)
public_key = private_key.public_key()

# 將密鑰轉換為 PEM 格式
private_pem = private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption()
)

public_pem = public_key.public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo
)

# OAuth2 Bearer Token 設定
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/oauth/token",
    scopes={
        "openid": "OpenID Connect 身份驗證",
        "profile": "存取個人資料",
        "email": "存取電子郵件地址",
        "read": "讀取基本資料",
        "write": "修改資料"
    }
)

# 儲存資料的簡單記憶體存儲（實際應用中應使用資料庫）
token_store: Dict[str, Dict] = {}
auth_code_store: Dict[str, Dict] = {}
client_store: Dict[str, Dict] = {}
refresh_token_store: Dict[str, Dict] = {}
user_store: Dict[str, Dict] = {}

# 預設的測試 Client
DEFAULT_CLIENTS = {
    "chainlit_app": {
        "client_id": "chainlit_app",
        "client_secret": os.getenv('FOOBAR_CLIENT_SECRET'),
        "redirect_uris": [
            "http://localhost:8000/auth/oauth/foobar/callback", 
        ],
        "scopes": ["openid", "profile", "email", "read", "write"],
        "name": "測試應用程式",
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "client_secret_basic"
    }
}

# 初始化預設 clients 和測試用戶
client_store.update(DEFAULT_CLIENTS)

# 測試用戶資料
DEFAULT_USERS = {
    "user_123": {
        "id": "user_123",
        "username": "testuser",
        "email": "test@example.com",
        "name": "測試用戶",
        "given_name": "測試",
        "family_name": "用戶",
        "picture": "https://api.dicebear.com/7.x/avataaars/svg?seed=testuser",
        "email_verified": True,
        "locale": "zh-TW",
        "updated_at": int(time.time())
    }
}

user_store.update(DEFAULT_USERS)

# 支援的 scopes
SUPPORTED_SCOPES = {
    "openid": "OpenID Connect 身份驗證",
    "profile": "存取個人資料",
    "email": "存取電子郵件地址",
    "read": "讀取基本資料",
    "write": "修改資料"
}

# Pydantic 模型
class AuthorizeRequest(BaseModel):
    response_type: str = Field(..., description="回應類型，必須是 'code'")
    client_id: str = Field(..., description="客戶端 ID")
    redirect_uri: str = Field(..., description="重定向 URI")
    scope: Optional[str] = Field(None, description="請求的權限範圍")
    state: Optional[str] = Field(None, description="狀態參數")
    code_challenge: Optional[str] = Field(None, description="PKCE 代碼挑戰")
    code_challenge_method: Optional[str] = Field(None, description="PKCE 代碼挑戰方法")
    nonce: Optional[str] = Field(None, description="OpenID Connect nonce")

class TokenRequest(BaseModel):
    grant_type: str = Field(..., description="授權類型")
    code: Optional[str] = Field(None, description="授權代碼")
    redirect_uri: Optional[str] = Field(None, description="重定向 URI")
    client_id: Optional[str] = Field(None, description="客戶端 ID")
    client_secret: Optional[str] = Field(None, description="客戶端密鑰")
    refresh_token: Optional[str] = Field(None, description="刷新令牌")
    code_verifier: Optional[str] = Field(None, description="PKCE 代碼驗證器")

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    refresh_token: Optional[str] = None
    scope: Optional[str] = None
    id_token: Optional[str] = None

class UserInfo(BaseModel):
    sub: str
    name: Optional[str] = None
    given_name: Optional[str] = None
    family_name: Optional[str] = None
    email: Optional[str] = None
    email_verified: Optional[bool] = None
    picture: Optional[str] = None
    locale: Optional[str] = None
    updated_at: Optional[int] = None

class ClientInfo(BaseModel):
    client_id: str
    name: str
    redirect_uris: List[str]
    scopes: List[str]

class ErrorResponse(BaseModel):
    error: str
    error_description: Optional[str] = None
    error_uri: Optional[str] = None

class OpenIDConfiguration(BaseModel):
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    userinfo_endpoint: str
    jwks_uri: str
    scopes_supported: List[str]
    response_types_supported: List[str]
    grant_types_supported: List[str]
    subject_types_supported: List[str]
    id_token_signing_alg_values_supported: List[str]
    token_endpoint_auth_methods_supported: List[str]

# 輔助函數
def validate_client(client_id: str, client_secret: Optional[str] = None) -> Dict:
    """驗證客戶端憑證"""
    client = client_store.get(client_id)
    if not client:
        raise HTTPException(
            status_code=401,
            detail="無效的客戶端 ID"
        )
    
    if client_secret and client.get("client_secret") != client_secret:
        raise HTTPException(
            status_code=401,
            detail="無效的客戶端密鑰"
        )
    
    return client

def validate_redirect_uri(client: Dict, redirect_uri: str) -> bool:
    """驗證重定向 URI"""
    return redirect_uri in client.get("redirect_uris", [])

def validate_scopes(requested_scopes: str, client_scopes: List[str]) -> List[str]:
    """驗證請求的權限範圍"""
    if not requested_scopes:
        return []
    
    scopes = requested_scopes.split()
    valid_scopes = []
    
    for scope in scopes:
        if scope in SUPPORTED_SCOPES and scope in client_scopes:
            valid_scopes.append(scope)
    
    return valid_scopes

def generate_authorization_code(client_id: str, user_id: str, redirect_uri: str, 
                              scopes: List[str], nonce: Optional[str] = None) -> str:
    """生成授權代碼"""
    code = secrets.token_urlsafe(32)
    
    auth_code_store[code] = {
        "client_id": client_id,
        "user_id": user_id,
        "redirect_uri": redirect_uri,
        "scopes": scopes,
        "nonce": nonce,
        "expires_at": datetime.now() + timedelta(minutes=10),
        "used": False
    }
    
    return code

def generate_tokens(client_id: str, user_id: str, scopes: List[str], 
                   nonce: Optional[str] = None) -> Dict[str, Any]:
    """生成訪問令牌和 ID 令牌"""
    # 生成訪問令牌
    access_token = secrets.token_urlsafe(32)
    refresh_token = secrets.token_urlsafe(32)
    expires_in = 3600  # 1小時
    
    # 儲存訪問令牌
    token_info = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": datetime.now() + timedelta(seconds=expires_in),
        "client_id": client_id,
        "user_id": user_id,
        "scopes": scopes
    }
    token_store[access_token] = token_info
    refresh_token_store[refresh_token] = token_info
    
    result = {
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": expires_in,
        "refresh_token": refresh_token,
        "scope": " ".join(scopes)
    }
    
    # 如果包含 openid scope，生成 ID 令牌
    if "openid" in scopes:
        id_token = generate_id_token(user_id, client_id, nonce, scopes)
        result["id_token"] = id_token
    
    return result

def generate_id_token(user_id: str, client_id: str, nonce: Optional[str] = None, 
                     scopes: List[str] = None) -> str:
    """生成 OpenID Connect ID 令牌"""
    user = user_store.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用戶不存在")
    
    now = datetime.now()
    
    # 基本聲明
    claims = {
        "iss": "http://localhost:8000",  # 發行者
        "sub": user_id,  # 主體（用戶 ID）
        "aud": client_id,  # 受眾（客戶端 ID）
        "exp": int((now + timedelta(hours=1)).timestamp()),  # 過期時間
        "iat": int(now.timestamp()),  # 發行時間
        "auth_time": int(now.timestamp()),  # 認證時間
    }
    
    # 添加 nonce（如果提供）
    if nonce:
        claims["nonce"] = nonce
    
    # 根據 scope 添加用戶信息
    if scopes:
        if "profile" in scopes:
            claims.update({
                "name": user.get("name"),
                "given_name": user.get("given_name"),
                "family_name": user.get("family_name"),
                "picture": user.get("picture"),
                "locale": user.get("locale"),
                "updated_at": user.get("updated_at")
            })
        
        if "email" in scopes:
            claims.update({
                "email": user.get("email"),
                "email_verified": user.get("email_verified")
            })
    
    # 使用 JWT 編碼
    return jwt.encode(claims, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

async def get_current_user(token: str = Depends(oauth2_scheme)) -> Dict:
    """驗證訪問令牌並返回用戶資訊"""
    token_info = token_store.get(token)
    if not token_info:
        raise HTTPException(
            status_code=401,
            detail="無效的訪問令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # 檢查令牌是否過期
    if datetime.now() > token_info["expires_at"]:
        del token_store[token]
        raise HTTPException(
            status_code=401,
            detail="訪問令牌已過期",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return token_info

# OpenID Connect Discovery 端點
@router.get("/.well-known/openid-configuration", response_model=OpenIDConfiguration)
async def openid_configuration(request: Request):
    """OpenID Connect Discovery 端點"""
    base_url = str(request.base_url).rstrip('/')
    
    return OpenIDConfiguration(
        issuer=base_url,
        authorization_endpoint=f"{base_url}/oauth/authorize",
        token_endpoint=f"{base_url}/oauth/token",
        userinfo_endpoint=f"{base_url}/oauth/userinfo",
        jwks_uri=f"{base_url}/oauth/.well-known/jwks.json",
        scopes_supported=list(SUPPORTED_SCOPES.keys()),
        response_types_supported=["code"],
        grant_types_supported=["authorization_code", "refresh_token"],
        subject_types_supported=["public"],
        id_token_signing_alg_values_supported=["HS256"],
        token_endpoint_auth_methods_supported=["client_secret_basic", "client_secret_post"]
    )

# JWKS 端點
@router.get("/.well-known/jwks.json")
async def jwks():
    """JSON Web Key Set 端點"""
    # 這裡應該返回公鑰信息，簡化實現
    return {
        "keys": [
            {
                "kty": "RSA",
                "use": "sig",
                "kid": "1",
                "alg": "HS256"
            }
        ]
    }

# 授權端點
@router.get("/authorize")
async def authorize(
    request: Request,
    response_type: str = Query(default='code'),
    client_id: str = Query(...),
    redirect_uri: str = Query(...),
    scope: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    code_challenge: Optional[str] = Query(None),
    code_challenge_method: Optional[str] = Query(None),
    nonce: Optional[str] = Query(None)
):
    """OAuth 2.0 授權端點"""
    
    # 驗證 response_type
    if response_type != "code":
        error_params = {
            "error": "unsupported_response_type",
            "error_description": "僅支援 'code' 回應類型"
        }
        if state:
            error_params["state"] = state
        
        error_url = f"{redirect_uri}?{urllib.parse.urlencode(error_params)}"
        return RedirectResponse(url=error_url, status_code=302)
    
    # 驗證客戶端
    try:
        client = validate_client(client_id)
    except HTTPException:
        error_params = {
            "error": "invalid_client",
            "error_description": "無效的客戶端 ID"
        }
        if state:
            error_params["state"] = state
        
        error_url = f"{redirect_uri}?{urllib.parse.urlencode(error_params)}"
        return RedirectResponse(url=error_url, status_code=302)
    
    # 驗證重定向 URI
    if not validate_redirect_uri(client, redirect_uri):
        raise HTTPException(
            status_code=400,
            detail="無效的重定向 URI"
        )
    
    # 驗證權限範圍
    requested_scopes = validate_scopes(scope or "", client["scopes"])
    
    # 模擬用戶登入和授權（實際應用中應該有登入頁面）
    user_id = "user_123"  # 模擬已登入用戶
    
    # 生成授權代碼
    auth_code = generate_authorization_code(
        client_id, user_id, redirect_uri, requested_scopes, nonce
    )
    
    # 重定向回客戶端
    callback_params = {"code": auth_code}
    if state:
        callback_params["state"] = state
    
    callback_url = f"{redirect_uri}?{urllib.parse.urlencode(callback_params)}"
    return RedirectResponse(url=callback_url, status_code=302)

# 令牌端點
@router.post("/token", response_model=TokenResponse)
async def token_endpoint(
    request: Request,
    grant_type: str = Form(...),
    code: Optional[str] = Form(None),
    redirect_uri: Optional[str] = Form(None),
    client_id: Optional[str] = Form(None),
    client_secret: Optional[str] = Form(None),
    refresh_token: Optional[str] = Form(None),
    code_verifier: Optional[str] = Form(None)
):
    """OAuth 2.0 令牌端點"""
    
    # 處理客戶端認證（Basic Auth 或 POST body）
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Basic "):
        # Basic Authentication
        try:
            credentials = base64.b64decode(auth_header[6:]).decode("utf-8")
            client_id, client_secret = credentials.split(":", 1)
        except Exception:
            raise HTTPException(
                status_code=401,
                detail="無效的客戶端認證"
            )
    
    if grant_type == "authorization_code":
        # 授權代碼流程
        if not all([code, redirect_uri, client_id]):
            raise HTTPException(
                status_code=400,
                detail="缺少必要參數"
            )
        
        # 驗證客戶端
        client = validate_client(client_id, client_secret)
        
        # 驗證授權代碼
        auth_code_info = auth_code_store.get(code)
        if not auth_code_info:
            raise HTTPException(
                status_code=400,
                detail="無效的授權代碼"
            )
        
        if auth_code_info["used"]:
            raise HTTPException(
                status_code=400,
                detail="授權代碼已被使用"
            )
        
        if datetime.now() > auth_code_info["expires_at"]:
            del auth_code_store[code]
            raise HTTPException(
                status_code=400,
                detail="授權代碼已過期"
            )
        
        if auth_code_info["client_id"] != client_id:
            raise HTTPException(
                status_code=400,
                detail="客戶端 ID 不匹配"
            )
        
        if auth_code_info["redirect_uri"] != redirect_uri:
            raise HTTPException(
                status_code=400,
                detail="重定向 URI 不匹配"
            )
        
        # 標記授權代碼為已使用
        auth_code_info["used"] = True
        
        # 生成令牌
        tokens = generate_tokens(
            client_id,
            auth_code_info["user_id"],
            auth_code_info["scopes"],
            auth_code_info.get("nonce")
        )
        
        return TokenResponse(**tokens)
    
    elif grant_type == "refresh_token":
        # 刷新令牌流程
        if not refresh_token:
            raise HTTPException(
                status_code=400,
                detail="缺少刷新令牌"
            )
        
        # 驗證刷新令牌
        token_info = refresh_token_store.get(refresh_token)
        if not token_info:
            raise HTTPException(
                status_code=400,
                detail="無效的刷新令牌"
            )
        
        # 驗證客戶端
        if client_id and token_info["client_id"] != client_id:
            raise HTTPException(
                status_code=400,
                detail="客戶端 ID 不匹配"
            )
        
        # 生成新的令牌
        tokens = generate_tokens(
            token_info["client_id"],
            token_info["user_id"],
            token_info["scopes"]
        )
        
        # 撤銷舊的刷新令牌
        del refresh_token_store[refresh_token]
        
        return TokenResponse(**tokens)
    
    else:
        raise HTTPException(
            status_code=400,
            detail="不支援的授權類型"
        )

# UserInfo 端點
@router.get("/userinfo", response_model=UserInfo)
async def userinfo_endpoint(current_user: Dict = Depends(get_current_user)):
    """OpenID Connect UserInfo 端點"""
    user_id = current_user["user_id"]
    scopes = current_user["scopes"]
    
    user = user_store.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用戶不存在")
    
    # 基本信息
    user_info = {"sub": user_id}
    
    # 根據 scope 返回相應信息
    if "profile" in scopes:
        user_info.update({
            "name": user.get("name"),
            "given_name": user.get("given_name"),
            "family_name": user.get("family_name"),
            "picture": user.get("picture"),
            "locale": user.get("locale"),
            "updated_at": user.get("updated_at")
        })
    
    if "email" in scopes:
        user_info.update({
            "email": user.get("email"),
            "email_verified": user.get("email_verified")
        })
    
    return UserInfo(**user_info)

# 令牌驗證端點
@router.get("/token/validate")
async def validate_token(request: Request):
    """驗證訪問令牌的有效性"""
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
            detail="無效的訪問令牌"
        )
    
    if datetime.now() > token_info["expires_at"]:
        del token_store[access_token]
        raise HTTPException(
            status_code=401,
            detail="訪問令牌已過期"
        )
    
    return {
        "valid": True,
        "expires_at": token_info["expires_at"].isoformat(),
        "user_id": token_info["user_id"],
        "client_id": token_info["client_id"],
        "scopes": token_info["scopes"]
    }

# 令牌撤銷端點
@router.post("/token/revoke")
async def revoke_token(
    token: str = Form(...),
    token_type_hint: Optional[str] = Form(None),
    client_id: Optional[str] = Form(None),
    client_secret: Optional[str] = Form(None)
):
    """撤銷訪問令牌或刷新令牌"""
    
    # 驗證客戶端（如果提供）
    if client_id:
        validate_client(client_id, client_secret)
    
    # 嘗試撤銷訪問令牌
    if token in token_store:
        del token_store[token]
        return {"message": "令牌已成功撤銷"}
    
    # 嘗試撤銷刷新令牌
    if token in refresh_token_store:
        del refresh_token_store[token]
        return {"message": "令牌已成功撤銷"}
    
    # RFC 7009 規定，即使令牌不存在也應該返回成功
    return {"message": "令牌已成功撤銷"}

# 客戶端管理端點
@router.get("/clients", response_model=List[ClientInfo])
async def list_clients():
    """列出所有註冊的客戶端"""
    clients = []
    for client_id, client_data in client_store.items():
        clients.append(ClientInfo(
            client_id=client_id,
            name=client_data["name"],
            redirect_uris=client_data["redirect_uris"],
            scopes=client_data["scopes"]
        ))
    return clients

@router.post("/clients", response_model=ClientInfo)
async def register_client(
    name: str = Form(...),
    redirect_uris: List[str] = Form(...),
    scopes: List[str] = Form(...)
):
    """註冊新的客戶端"""
    client_id = f"client_{secrets.token_hex(8)}"
    client_secret = secrets.token_urlsafe(32)
    
    # 驗證權限範圍
    valid_scopes = [scope for scope in scopes if scope in SUPPORTED_SCOPES]
    
    client_data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "name": name,
        "redirect_uris": redirect_uris,
        "scopes": valid_scopes,
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "client_secret_post"
    }
    
    client_store[client_id] = client_data
    
    return ClientInfo(
        client_id=client_id,
        name=name,
        redirect_uris=redirect_uris,
        scopes=valid_scopes
    )

# 測試端點
@router.get("/test")
async def test_endpoint():
    """測試端點，返回當前系統狀態"""
    return {
        "message": "OAuth 2.0 和 OpenID Connect 服務運行正常",
        "active_tokens": len(token_store),
        "active_codes": len(auth_code_store),
        "registered_clients": len(client_store),
        "supported_scopes": list(SUPPORTED_SCOPES.keys()),
        "endpoints": {
            "authorization": "/oauth/authorize",
            "token": "/oauth/token",
            "userinfo": "/oauth/userinfo",
            "discovery": "/oauth/.well-known/openid-configuration",
            "jwks": "/oauth/.well-known/jwks.json"
        }
    }
