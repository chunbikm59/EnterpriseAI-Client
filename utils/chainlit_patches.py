"""
啟動時自動 patch Chainlit 前端 bundle，修復在非 Secure Context（http://IP:port）
下 navigator.clipboard.writeText() 無法使用的問題。

原因：瀏覽器 Clipboard API 要求 Secure Context（HTTPS 或 localhost），
      用 http://IP:port 時 navigator.clipboard 不可用，複製功能完全失效。
修法：將三處 clipboard.writeText(y) 替換成帶 execCommand fallback 的版本，
      優先用 Clipboard API，失敗時改用 document.execCommand('copy')。
"""

import logging
import pathlib

logger = logging.getLogger(__name__)

# 用 textarea + execCommand 做 clipboard fallback 的 inline async IIFE
# 優先嘗試 navigator.clipboard.writeText，失敗或不可用時改用 execCommand
_COPY_HELPER = (
    "(async t=>{try{if(navigator.clipboard){await navigator.clipboard.writeText(t);return}}catch(e){}"
    "const el=document.createElement('textarea');el.value=t;"
    "el.style.cssText='position:fixed;opacity:0;top:0;left:0';"
    "document.body.appendChild(el);el.select();"
    "try{document.execCommand('copy')}finally{document.body.removeChild(el)}})(y)"
)

_PATCHES: list[tuple[str, str]] = [
    # copilot 分支（原始 / 已有 .catch 兩種情況都列出）
    (
        "if(c)await navigator.clipboard.writeText(y).catch(()=>{});",
        f"if(c)await {_COPY_HELPER};",
    ),
    (
        "if(c)await navigator.clipboard.writeText(y);",
        f"if(c)await {_COPY_HELPER};",
    ),
    # 已分享時直接複製分支
    (
        "d(n),await navigator.clipboard.writeText(y).catch(()=>{}),l(!0),s(!0)",
        f"d(n),await {_COPY_HELPER},l(!0),s(!0)",
    ),
    (
        "d(n),await navigator.clipboard.writeText(y),l(!0),s(!0)",
        f"d(n),await {_COPY_HELPER},l(!0),s(!0)",
    ),
    # 新建分享後複製分支
    (
        "d(n),await navigator.clipboard.writeText(y).catch(()=>{}),await new Promise",
        f"d(n),await {_COPY_HELPER},await new Promise",
    ),
    (
        "d(n),await navigator.clipboard.writeText(y),await new Promise",
        f"d(n),await {_COPY_HELPER},await new Promise",
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
