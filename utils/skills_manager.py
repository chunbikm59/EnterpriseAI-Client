"""AgentSkills 技能管理模組。

負責技能的發現、解析、目錄產生與序列化。

流程概要：
  1. discover_skills(user_id)         — 掃描使用者 skills/ 資料夾
  2. build_skill_catalog_json(skills)  — 產生注入 system prompt 的 JSON 目錄
  3. skills_to_json / skills_from_json — 跨模組序列化（供 buildin.py session registry 使用）
  4. get_skill_content(name, skills)   — 讀取 SKILL.md body（activate_skill 呼叫時使用）

SKILL.md 格式參考 agentskills/ 中的 Agent Skills Spec：
  - 檔案開頭為 YAML frontmatter（--- 包圍），必須含 name 與 description
  - frontmatter 之後為 Markdown body，即技能的完整指令內容
"""
import json
import os
import warnings
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

import yaml  # PyYAML，已在 requirements.txt 中

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ── SKILL.md 解析工具（參考 agentskills/skills-ref 重寫，不直接依賴該專案） ──

def _find_skill_md(skill_dir: Path) -> Optional[Path]:
    """在技能資料夾中尋找 SKILL.md，優先大寫，也接受小寫。"""
    for name in ("SKILL.md", "skill.md"):
        path = skill_dir / name
        if path.exists():
            return path
    return None


def _parse_frontmatter(content: str) -> tuple[dict, str]:
    """解析 SKILL.md 的 YAML frontmatter。

    Args:
        content: SKILL.md 的原始文字內容。

    Returns:
        (metadata dict, markdown body) 的 tuple。

    Raises:
        ValueError: frontmatter 格式不正確或 YAML 解析失敗。
    """
    if not content.startswith("---"):
        raise ValueError("SKILL.md must start with YAML frontmatter (---)")

    parts = content.split("---", 2)
    if len(parts) < 3:
        raise ValueError("SKILL.md frontmatter not properly closed with ---")

    frontmatter_str = parts[1]
    body = parts[2].strip()

    metadata = yaml.safe_load(frontmatter_str)
    if not isinstance(metadata, dict):
        raise ValueError("SKILL.md frontmatter must be a YAML mapping")

    return metadata, body


# ── 資料模型 ──

@dataclass
class SkillInfo:
    """單一技能的摘要資訊。"""
    name: str          # 技能名稱（對應 SKILL.md frontmatter 中的 name）
    description: str   # 技能描述（用於 system prompt 讓 LLM 判斷是否啟用）
    location: str      # 技能目錄路徑（agentskills spec 定義的 hint）
    skill_dir: str     # 技能目錄的絕對路徑
    source: str = "user"  # 技能來源："user"（用戶技能）| "system"（系統技能）


# ── 技能掃描與發現 ──

def _scan_skills_dir(skills_dir: str, source: str = "user") -> list[SkillInfo]:
    """掃描指定目錄下的所有技能子資料夾。

    採用 lenient 策略：解析失敗只發出 warning，不會中斷其他技能的載入。
    """
    results = []
    if not os.path.isdir(skills_dir):
        return results

    for entry in os.listdir(skills_dir):
        skill_dir = os.path.join(skills_dir, entry)
        if not os.path.isdir(skill_dir):
            continue

        # 找 SKILL.md（大小寫皆可）
        skill_md = _find_skill_md(Path(skill_dir))
        if skill_md is None:
            continue

        try:
            content = skill_md.read_text(encoding="utf-8")
            metadata, _ = _parse_frontmatter(content)
            name = metadata.get("name", "").strip()
            description = metadata.get("description", "").strip()
            if not name or not description:
                warnings.warn(f"Skill at {skill_dir} missing name or description, skipping.")
                continue
            results.append(SkillInfo(
                name=name,
                description=description,
                location=skill_dir,
                skill_dir=skill_dir,
                source=source,
            ))
        except Exception as e:
            warnings.warn(f"Failed to parse skill at {skill_dir}: {e}")

    return results


SYSTEM_SKILLS_DIR = os.path.join(PROJECT_ROOT, "system_skills")


def discover_system_skills() -> list[SkillInfo]:
    """發現所有系統技能。

    掃描 system_skills/ 目錄下的所有子資料夾，全部自動啟用。
    管理員只需將技能資料夾放入 system_skills/ 即可生效。
    """
    return _scan_skills_dir(SYSTEM_SKILLS_DIR, source="system")


def discover_skills(user_id: str) -> list[SkillInfo]:
    """發現使用者可用的所有技能（系統技能 + 用戶技能）。

    系統技能來自 system_skills/，用戶技能來自 user_profiles/{user_id}/skills/。
    """
    from utils.user_profile import get_user_skills_dir
    user_skills_dir = get_user_skills_dir(user_id)
    user_skills = _scan_skills_dir(user_skills_dir, source="user")
    system_skills = discover_system_skills()
    return system_skills + user_skills  # 系統技能在前


# ── 目錄產生與序列化 ──

def build_skill_catalog_json(skills: list[SkillInfo]) -> str:
    """將技能清單轉為 JSON 字串，用於注入 system prompt。

    只包含 name、description、location，不含 skill_dir 等內部欄位。
    """
    catalog = [
        {"name": s.name, "description": s.description, "location": s.location}
        for s in skills
    ]
    return json.dumps(catalog, ensure_ascii=False, indent=2)


def get_skill_content(skill_name: str, skills: list[SkillInfo]) -> Optional[str]:
    """根據技能名稱取得 SKILL.md 的 Markdown body（去除 frontmatter）。

    Returns:
        Markdown body 字串，找不到技能時回傳 None。
    """
    skill_map = {s.name: s for s in skills}
    skill = skill_map.get(skill_name)
    if skill is None:
        return None
    skill_md = _find_skill_md(Path(skill.skill_dir))
    if skill_md is None:
        return None
    content = skill_md.read_text(encoding="utf-8")
    _, body = _parse_frontmatter(content)
    return body


def skills_to_json(skills: list[SkillInfo]) -> str:
    """將 SkillInfo 清單序列化為 JSON，供跨模組傳遞（如 buildin.py session registry）。"""
    return json.dumps([asdict(s) for s in skills], ensure_ascii=False)


def skills_from_json(json_str: str) -> list[SkillInfo]:
    """從 JSON 字串反序列化為 SkillInfo 清單。相容舊版無 source 欄位的格式。"""
    data = json.loads(json_str)
    return [SkillInfo(
        name=item["name"],
        description=item["description"],
        location=item["location"],
        skill_dir=item["skill_dir"],
        source=item.get("source", "user"),
    ) for item in data]
