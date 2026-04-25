"""本地檔案系統 storage client，供 Chainlit data layer 使用。

上傳的元素檔案存放在 PROJECT_ROOT/chainlit_uploads/{object_key}，
並透過 FastAPI 的 /api/uploads/{object_key} 路由對外提供服務。
"""
import os
from typing import Any, Dict, Union

from chainlit.data.storage_clients.base import BaseStorageClient


class LocalStorageClient(BaseStorageClient):
    def __init__(self, storage_dir: str, base_url: str):
        self.storage_dir = storage_dir
        self.base_url = base_url.rstrip("/")

    async def upload_file(
        self,
        object_key: str,
        data: Union[bytes, str],
        mime: str = "application/octet-stream",
        overwrite: bool = True,
        content_disposition: str | None = None,
    ) -> Dict[str, Any]:
        dest = os.path.join(self.storage_dir, object_key)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        if not overwrite and os.path.exists(dest):
            return {"object_key": object_key, "url": f"{self.base_url}/{object_key}"}
        mode = "wb" if isinstance(data, bytes) else "w"
        with open(dest, mode) as f:
            f.write(data)
        return {"object_key": object_key, "url": f"{self.base_url}/{object_key}"}

    async def get_read_url(self, object_key: str) -> str:
        return f"{self.base_url}/{object_key}"

    async def delete_file(self, object_key: str) -> bool:
        dest = os.path.join(self.storage_dir, object_key)
        if not os.path.exists(dest):
            return False
        os.remove(dest)
        return True

    async def close(self) -> None:
        pass
