import re
import os
from agent_tools._context import mcp, _session_skill_catalogs
from utils.skills_manager import (
    _parse_frontmatter as _pfm,
    discover_skills as _discover_skills,
    skills_to_json as _s2j,
)


def register_session_skills(session_id: str, skills_json: str):
    """在 on_chat_start 時將該 session 的技能目錄（JSON）註冊進來。"""
    _session_skill_catalogs[session_id] = skills_json


def unregister_session_skills(session_id: str):
    """在 on_chat_end 時清除該 session 的技能資料。"""
    _session_skill_catalogs.pop(session_id, None)


def register_mcp_tool(func_name: str, describe: str, return_string, namespace=None):
    if namespace is None:
        namespace = globals()

    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', func_name):
        raise ValueError("函數名稱不合法，請使用英文、數字、底線組合，且不得以數字開頭")

    safe_return = repr(return_string)

    func_code = f'''
@mcp.tool()
def {func_name}():
    """{describe}"""
    return {safe_return}
'''

    exec(func_code, namespace)
    return namespace[func_name]


_SKILL_ALLOWED_FIELDS = {"name", "description", "license", "allowed-tools", "metadata", "compatibility"}


def _validate_skill_frontmatter(metadata: dict, skill_dir_name: str) -> list[str]:
    import unicodedata as _ud
    errors = []
    extra = set(metadata.keys()) - _SKILL_ALLOWED_FIELDS
    if extra:
        errors.append(f"frontmatter 含不允許的欄位：{', '.join(sorted(extra))}。允許欄位：{sorted(_SKILL_ALLOWED_FIELDS)}")
    if "name" not in metadata:
        errors.append("缺少必填欄位：name")
    else:
        name = str(metadata["name"]).strip()
        name = _ud.normalize("NFKC", name)
        if len(name) == 0:
            errors.append("name 不能為空")
        elif len(name) > 64:
            errors.append(f"name 超過 64 字元限制（目前 {len(name)} 字元）")
        elif name != name.lower():
            errors.append("name 必須全小寫")
        elif name.startswith("-") or name.endswith("-"):
            errors.append("name 不能以連字符開頭或結尾")
        elif "--" in name:
            errors.append("name 不能含連續連字符")
        elif not all(c.isalnum() or c == "-" for c in name):
            errors.append(f"name '{name}' 含非法字元，只允許字母、數字、連字符")
        elif _ud.normalize("NFKC", skill_dir_name) != name:
            errors.append(f"技能目錄名稱 '{skill_dir_name}' 必須與 name '{name}' 完全相符")
    if "description" not in metadata:
        errors.append("缺少必填欄位：description")
    else:
        desc = str(metadata.get("description", "")).strip()
        if not desc:
            errors.append("description 不能為空")
        elif len(desc) > 1024:
            errors.append(f"description 超過 1024 字元限制（目前 {len(desc)} 字元）")
    if "compatibility" in metadata:
        compat = str(metadata["compatibility"])
        if len(compat) > 500:
            errors.append(f"compatibility 超過 500 字元限制（目前 {len(compat)} 字元）")
    return errors


async def _write_skill_file(target_abs: str, user_skills_abs: str, content: str, session_id: str, user_id: str) -> str:
    from agent_tools._path_utils import _PROJECT_ROOT
    os.makedirs(os.path.dirname(target_abs), exist_ok=True)
    with open(target_abs, "w", encoding="utf-8") as f:
        f.write(content)

    fname = os.path.basename(target_abs)
    if fname not in ("SKILL.md", "skill.md"):
        rel = os.path.relpath(target_abs, _PROJECT_ROOT).replace("\\", "/")
        return f"檔案已寫入：{rel}"

    try:
        metadata, _ = _pfm(content)
    except ValueError as e:
        return f"SKILL.md 格式錯誤：{e}"

    skill_dir_name = os.path.basename(os.path.dirname(target_abs))
    errors = _validate_skill_frontmatter(metadata, skill_dir_name)
    if errors:
        return "SKILL.md 驗證失敗，請修正以下錯誤後重新寫入：\n" + "\n".join(f"- {e}" for e in errors)

    updated_skills = _discover_skills(user_id)
    if session_id:
        _session_skill_catalogs[session_id] = _s2j(updated_skills)

    skill_name = metadata["name"]
    return (
        f"技能 '{skill_name}' 已成功建立並通過驗證。\n"
        f"本次對話可立即使用 activate_skill('{skill_name}') 啟用此技能。\n"
        f"下次對話開始時，技能將自動出現在可用技能清單中。"
    )
