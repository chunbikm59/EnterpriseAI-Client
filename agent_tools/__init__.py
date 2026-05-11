# 觸發所有 @mcp.tool() 裝飾器（副作用 import）
from agent_tools import files, youtube, http, skills, media, render  # noqa: F401

from agent_tools._context import (
    mcp,
    _session_ctx,
    _session_skill_catalogs,
    _pending_forms,
    _pending_renders,
    _pending_md_renders,
    _pptx_upload_events,
    get_conversation_folder,
)
from agent_tools._skill_utils import register_session_skills, unregister_session_skills
from agent_tools.files import list_files, read_file, write_file, grep_files, edit_file, delete_file
from agent_tools.youtube import download_youtube, list_youtube_subtitles
from agent_tools.http import http_request
from agent_tools.skills import activate_skill
from agent_tools.media import capture_video_frames, capture_ppt_slides
from agent_tools.render import ask_user_question, render_html, render_pptx

_FUNC_MAP: dict = {
    "list_files": list_files,
    "read_file": read_file,
    "download_youtube": download_youtube,
    "list_youtube_subtitles": list_youtube_subtitles,
    "http_request": http_request,
    "activate_skill": activate_skill,
    "write_file": write_file,
    "grep_files": grep_files,
    "edit_file": edit_file,
    "delete_file": delete_file,
    "ask_user_question": ask_user_question,
    "capture_video_frames": capture_video_frames,
    "capture_ppt_slides": capture_ppt_slides,
    "render_html": render_html,
    "render_pptx": render_pptx,
}

__all__ = [
    "mcp", "_session_ctx", "_session_skill_catalogs",
    "_pending_forms", "_pending_renders", "_pending_md_renders", "_pptx_upload_events",
    "get_conversation_folder",
    "register_session_skills", "unregister_session_skills",
    "_FUNC_MAP",
    "list_files", "read_file", "write_file", "grep_files", "edit_file", "delete_file",
    "download_youtube", "list_youtube_subtitles",
    "http_request",
    "activate_skill",
    "capture_video_frames", "capture_ppt_slides",
    "ask_user_question", "render_html", "render_pptx",
]
