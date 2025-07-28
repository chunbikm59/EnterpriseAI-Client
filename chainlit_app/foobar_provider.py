import os
import httpx
from fastapi import HTTPException
from chainlit.user import User
from chainlit.oauth_providers import OAuthProvider
import json
import logging

logger = logging.getLogger(__name__)

class FooBarProvider(OAuthProvider):
    id="foobar"
    env = [
        "FOOBAR_CLIENT_ID",
        "FOOBAR_CLIENT_SECRET"
    ]

    authorize_url=f"http://127.0.0.1:8000/api/oauth/authorize"
    token_url=f"http://127.0.0.1:8000/api/oauth/token"
    userinfo_url=f"http://127.0.0.1:8000/api/oauth/userinfo"
    authorize_params = {}
    
    def __init__(self):
        self.client_id = os.environ.get("FOOBAR_CLIENT_ID", "test_client_id")
        self.client_secret = os.environ.get("FOOBAR_CLIENT_SECRET", "test_client_secret")
        self.authorize_params = {
            "scope": "openid profile email read",
        }
    
    async def get_token(self, code: str, url: str) -> str:
        """
        使用授權代碼交換訪問令牌
        """
        try:
            # 從回調 URL 中提取 redirect_uri
            redirect_uri = url.split('?')[0] if '?' in url else url
            
            payload = {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": self.client_id,
                "client_secret": self.client_secret
            }
            
            logger.info(f"正在交換令牌，code: {code[:10]}..., redirect_uri: {redirect_uri}")
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.token_url,
                    data=payload,
                    headers={"Content-Type": "application/x-www-form-urlencoded"}
                )
                
                if response.status_code == 200:
                    token_data = response.json()
                    access_token = token_data.get("access_token")
                    logger.info(f"成功獲取訪問令牌: {access_token[:10]}...")
                    return access_token
                else:
                    error_msg = f"令牌交換失敗: {response.status_code} - {response.text}"
                    logger.error(error_msg)
                    raise HTTPException(status_code=response.status_code, detail=error_msg)
                    
        except httpx.RequestError as e:
            error_msg = f"令牌交換請求失敗: {str(e)}"
            logger.error(error_msg)
            raise HTTPException(status_code=500, detail=error_msg)
        except Exception as e:
            error_msg = f"令牌交換過程中發生錯誤: {str(e)}"
            logger.error(error_msg)
            raise HTTPException(status_code=500, detail=error_msg)

    async def get_user_info(self, token: str):
        """
        使用訪問令牌獲取用戶資訊
        """
        try:
            logger.info(f"正在獲取用戶資訊，token: {token[:10]}...")
            
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    self.userinfo_url,
                    headers={"Authorization": f"Bearer {token}"}
                )
                
                if response.status_code == 200:
                    user_data = response.json()
                    logger.info(f"成功獲取用戶資訊: {user_data}")
                    
                    # 創建 Chainlit User 對象
                    user = User(
                        identifier=user_data.get("sub", "unknown"),
                        metadata={
                            "image": user_data.get("picture", "public/B2CLogo.png"),
                            "provider": "foobar",
                            "name": user_data.get("name", "Unknown User"),
                            "email": user_data.get("email", ""),
                            "given_name": user_data.get("given_name", ""),
                            "family_name": user_data.get("family_name", ""),
                            "locale": user_data.get("locale", "zh-TW")
                        }
                    )
                    
                    # 返回用戶資料和 User 對象
                    user_info = {
                        "employee_id": user_data.get("sub", "unknown"),
                        "name": user_data.get("name", "Unknown User"),
                        "email": user_data.get("email", ""),
                        "given_name": user_data.get("given_name", ""),
                        "family_name": user_data.get("family_name", ""),
                        "picture": user_data.get("picture", ""),
                        "locale": user_data.get("locale", "zh-TW"),
                        "email_verified": user_data.get("email_verified", False)
                    }
                    
                    return user_info, user
                    
                else:
                    error_msg = f"獲取用戶資訊失敗: {response.status_code} - {response.text}"
                    logger.error(error_msg)
                    raise HTTPException(status_code=response.status_code, detail=error_msg)
                    
        except httpx.RequestError as e:
            error_msg = f"獲取用戶資訊請求失敗: {str(e)}"
            logger.error(error_msg)
            raise HTTPException(status_code=500, detail=error_msg)
        except Exception as e:
            error_msg = f"獲取用戶資訊過程中發生錯誤: {str(e)}"
            logger.error(error_msg)
            # 如果發生錯誤，返回預設用戶資訊
            user = User(
                identifier='unknown_user',
                metadata={
                    "image": 'public/B2CLogo.png', 
                    "provider": "foobar",
                    "name": "Unknown User",
                    "error": str(e)
                }
            )
            return {"employee_id": "unknown", "name": "Unknown User", "error": str(e)}, user
