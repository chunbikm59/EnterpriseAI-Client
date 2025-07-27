import os
import httpx
from fastapi import HTTPException
from chainlit.user import User
from chainlit.oauth_providers import OAuthProvider
import json

class FooBarProvider(OAuthProvider):
    id="foobar"
    env = [
    ]

    authorize_url=f"http://127.0.0.1:8000/api/oauth/mock-oauth-proveder"
    token_url=f"https://get.your/token_url"
    authorize_params = {}
    def __init__(self):
        self.client_id = os.environ.get("YOUR_ENV_VAR_NAMES")
        self.authorize_params = {
            "scope": "user:email",
        }
    async def get_token(self, code: str, url: str) -> str:
        payload = { "foo": self.client_id }
        return "token"
        # async with httpx.AsyncClient() as client:
        #     response = await client.post(
        #         self.token_url,
        #         data=payload
        #     )
            # do stuff, return a token

    async def get_user_info(self, token: str):
        # async with httpx.AsyncClient() as client:
        user = User(
            identifier='Leo',
            metadata={"image": 'public/B2CLogo.png', "provider": "foobar"},
        )
            # do stuff with the token and return a user, User tuple
        return {"employee_id":"2004036", "name": "user1"}, user