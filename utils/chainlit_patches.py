"""
啟動時自動 patch Chainlit 前端 bundle，修復在非 Secure Context（http://IP:port）
下 navigator.clipboard.writeText() 拋例外導致「建立分享連結失敗」的問題。

原因：瀏覽器 Clipboard API 要求 Secure Context（HTTPS 或 localhost），
      用 http://IP:port 時 clipboard 操作失敗，被 catch 後誤報失敗訊息。
修法：為三處 clipboard.writeText(y) 加上 .catch(()=>{}) fallback。
"""

import glob
import logging
import pathlib

logger = logging.getLogger(__name__)

_PATCHES: list[tuple[str, str]] = [
    # copilot 分支
    (
        "if(c)await navigator.clipboard.writeText(y);",
        "if(c)await navigator.clipboard.writeText(y).catch(()=>{});",
    ),
    # 已分享時直接複製分支
    (
        "d(n),await navigator.clipboard.writeText(y),l(!0),s(!0)",
        "d(n),await navigator.clipboard.writeText(y).catch(()=>{}),l(!0),s(!0)",
    ),
    # 新建分享後複製分支
    (
        "d(n),await navigator.clipboard.writeText(y),await new Promise",
        "d(n),await navigator.clipboard.writeText(y).catch(()=>{}),await new Promise",
    ),
]


def _find_chainlit_js() -> pathlib.Path | None:
    try:
        import chainlit
        frontend_dir = pathlib.Path(chainlit.__file__).parent / "frontend" / "dist" / "assets"
        candidates = list(frontend_dir.glob("index-*.js"))
        return candidates[0] if candidates else None
    except Exception:
        return None


def apply_clipboard_patch() -> None:
    js_path = _find_chainlit_js()
    if js_path is None:
        logger.warning("[chainlit_patches] 找不到 Chainlit frontend JS，略過 clipboard patch")
        return

    try:
        content = js_path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        logger.warning("[chainlit_patches] 無法讀取 %s：%s", js_path, e)
        return

    patched = content
    applied: list[str] = []
    skipped: list[str] = []

    for old, new in _PATCHES:
        if new in patched:
            skipped.append(old[:40])
        elif old in patched:
            patched = patched.replace(old, new, 1)
            applied.append(old[:40])
        else:
            logger.warning("[chainlit_patches] 找不到 patch 目標（可能 Chainlit 版本已更新）：%s…", old[:60])

    if not applied:
        if skipped:
            logger.debug("[chainlit_patches] clipboard patch 已套用，無需重新寫入")
        return

    try:
        js_path.write_text(patched, encoding="utf-8")
        logger.info("[chainlit_patches] clipboard patch 已套用：%s", ", ".join(f"'{s}…'" for s in applied))
    except OSError as e:
        logger.warning("[chainlit_patches] 無法寫入 %s：%s", js_path, e)
