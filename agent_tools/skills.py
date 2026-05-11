import os
import json
from pydantic import Field
from agent_tools._context import mcp, _session_ctx, _session_skill_catalogs
from agent_tools._path_utils import _PROJECT_ROOT
from utils.skills_manager import skills_from_json, get_skill_content

RESOURCES_MAX = 50


@mcp.tool()
async def activate_skill(
    skill_name: str = Field(description="技能名稱，與可用技能清單中的 name 相同")
) -> str:
    """載入指定技能的完整指令。當任務符合某個技能的描述時呼叫此工具。"""

    session_id = _session_ctx.get()["session_id"]
    print('session_id', session_id)

    skills_json = _session_skill_catalogs.get(session_id, "")
    if not skills_json:
        return "錯誤：此 session 無可用技能。"

    skills = skills_from_json(skills_json)
    body = get_skill_content(skill_name, skills)

    if body is None:
        available = ", ".join(s.name for s in skills)
        return f"錯誤：找不到技能 '{skill_name}'。可用技能：{available}"

    skill_map = {s.name: s for s in skills}
    skill = skill_map[skill_name]

    resources = []
    truncated = False
    for subdir in ("scripts", "references", "assets"):
        subdir_path = os.path.join(skill.skill_dir, subdir)
        if os.path.isdir(subdir_path):
            for dirpath, _dirnames, filenames in os.walk(subdir_path):
                for fname in filenames:
                    if len(resources) >= RESOURCES_MAX:
                        truncated = True
                        break
                    abs_file = os.path.join(dirpath, fname)
                    rel_path = os.path.relpath(abs_file, _PROJECT_ROOT).replace("\\", "/")
                    resources.append(rel_path)
                if truncated:
                    break
        if truncated:
            break

    resources_info = {"files": resources}
    if truncated:
        resources_info["note"] = f"listing truncated, {RESOURCES_MAX}+ files in directory"

    _SKILL_ENV_WHITELIST = ["BASE_URL"]
    for _key in _SKILL_ENV_WHITELIST:
        _val = os.getenv(_key, "")
        body = body.replace(f"${{{_key}}}", _val)

    skill_dir_rel = os.path.relpath(skill.skill_dir, _PROJECT_ROOT).replace("\\", "/")
    return (
        f"{body}\n\n"
        f"---\n"
        f"技能目錄: {skill_dir_rel}\n"
        f"可用資源: {json.dumps(resources_info, ensure_ascii=False)}"
    )
