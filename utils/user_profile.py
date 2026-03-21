"""使用者 Profile 目錄管理模組。

負責管理每位使用者的個人資料夾結構：
    user_profiles/
      └── {employee_id}/        # 使用者 profile 根目錄
           ├── skills/          # 已安裝的 AgentSkills
           └── (未來擴充：memory/, history/, settings/ …)
"""
import os

# 專案根目錄（此檔位於 utils/ 下，所以往上一層）
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 所有使用者 profile 的總根目錄
USER_PROFILES_ROOT = os.path.join(PROJECT_ROOT, "user_profiles")


def get_user_profile_dir(user_id: str) -> str:
    """取得指定使用者的 profile 資料夾路徑。

    會將 user_id 中的特殊字元替換為底線，確保路徑安全。
    """
    safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in user_id)
    return os.path.join(USER_PROFILES_ROOT, safe_id)


def get_user_skills_dir(user_id: str) -> str:
    """取得指定使用者的 skills 資料夾路徑。"""
    return os.path.join(get_user_profile_dir(user_id), "skills")


def ensure_profile_exists(user_id: str) -> dict:
    """確保使用者的 profile 資料夾結構存在，不存在則自動建立。

    Returns:
        dict: 包含 profile_dir 與 skills_dir 路徑。
    """
    profile_dir = get_user_profile_dir(user_id)
    skills_dir = get_user_skills_dir(user_id)
    os.makedirs(skills_dir, exist_ok=True)
    return {"profile_dir": profile_dir, "skills_dir": skills_dir}
