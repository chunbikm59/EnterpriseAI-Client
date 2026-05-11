import os
import json
import asyncio
import shutil
import subprocess
import zipfile
from pathlib import Path
from pydantic import Field
import defusedxml.minidom
from PIL import Image, ImageDraw, ImageFont
from agent_tools._context import mcp, _session_ctx, get_conversation_folder
from agent_tools._path_utils import _resolve_file_path, _resolve_user_path, _check_path_in_allowed_roots, _PROJECT_ROOT
from utils.user_profile import get_user_profile_dir, get_conversation_artifacts_dir

_GRID_THUMBNAIL_WIDTH = 600
_GRID_MAX_COLS = 6
_GRID_JPEG_QUALITY = 95
_GRID_PADDING = 20
_GRID_BORDER_WIDTH = 2
_GRID_FONT_SIZE_RATIO = 0.10
_GRID_LABEL_PADDING_RATIO = 0.4


@mcp.tool()
async def capture_video_frames(
    video_path: str = Field(description="影片檔案路徑（相對於對話資料夾，或 artifacts/ 子路徑）"),
    timestamps: list[str] = Field(description=(
        "要截圖的時間點列表，支援格式：\n"
        "- 秒數字串：'10', '75.5'\n"
        "- HH:MM:SS 或 MM:SS：'00:01:30', '1:30'"
    )),
) -> str:
    """使用 ffmpeg 對影片指定時間點截圖，回傳 base64 編碼的圖片（儲存於 artifacts/）。

    回傳格式為 JSON：{"__image_files__": {timestamp: abs_path}, "summary": "..."}
    其中 timestamp 為輸入的時間點字串，abs_path 為截圖的絕對路徑（由 agent 自動讀入上下文）。
    """

    if not shutil.which("ffmpeg"):
        return "錯誤：找不到 ffmpeg，請確認系統已安裝 ffmpeg 並加入 PATH。"

    root_folder = get_conversation_folder()
    artifacts_dir = get_conversation_artifacts_dir(root_folder)

    video_abs = _resolve_file_path(video_path, root_folder)
    if not _check_path_in_allowed_roots(video_abs, [os.path.realpath(root_folder)]):
        return "存取拒絕：只能存取對話資料夾中的影片。"

    if not os.path.isfile(video_abs):
        return f"影片檔案不存在：{video_path}"

    if not timestamps:
        return "錯誤：timestamps 不能為空。"

    os.makedirs(artifacts_dir, exist_ok=True)
    base_name = os.path.splitext(os.path.basename(video_abs))[0]

    successful_frames = []
    errors = []

    def _run_ffmpeg(ts: str, output_path: str):
        cmd = [
            "ffmpeg", "-y",
            "-ss", ts,
            "-i", video_abs,
            "-frames:v", "1",
            "-q:v", "2",
            output_path,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return proc.returncode, proc.stderr

    for ts in timestamps:
        ts_safe = ts.replace(":", "-").replace(".", "_")
        out_filename = f"{base_name}_frame_{ts_safe}.jpg"
        out_abs = os.path.join(artifacts_dir, out_filename)

        try:
            returncode, stderr = await asyncio.to_thread(_run_ffmpeg, ts, out_abs)
            if returncode == 0 and os.path.isfile(out_abs):
                successful_frames.append((ts, out_abs))
            else:
                errors.append(f"{ts}: ffmpeg 失敗 — {stderr.strip()[-200:]}")
        except subprocess.TimeoutExpired:
            errors.append(f"{ts}: 截圖逾時")
        except Exception as e:
            errors.append(f"{ts}: {str(e)}")

    summary_lines = [f"截圖完成（{len(successful_frames)} 張）："]
    frames_paths: dict[str, str] = {}
    for ts, abs_path in successful_frames:
        summary_lines.append(f"  artifacts/{os.path.basename(abs_path)} (時間點: {ts})")
        frames_paths[ts] = abs_path
    if errors:
        summary_lines.append(f"\n失敗（{len(errors)} 筆）：")
        summary_lines.extend(f"  {e}" for e in errors)

    return json.dumps({
        "__image_files__": frames_paths,
        "summary": "\n".join(summary_lines),
    }, ensure_ascii=False)


def _get_slide_info(pptx_path: str) -> list[dict]:
    """從 PPTX XML 讀取投影片順序與隱藏狀態。回傳 [{"name": "slide1.xml", "hidden": False}, ...]。"""
    with zipfile.ZipFile(pptx_path, "r") as zf:
        rels_content = zf.read("ppt/_rels/presentation.xml.rels").decode("utf-8")
        rels_dom = defusedxml.minidom.parseString(rels_content)

        rid_to_slide: dict[str, str] = {}
        for rel in rels_dom.getElementsByTagName("Relationship"):
            rid = rel.getAttribute("Id")
            target = rel.getAttribute("Target")
            rel_type = rel.getAttribute("Type")
            if "slide" in rel_type and target.startswith("slides/") and "slideLayout" not in rel_type:
                rid_to_slide[rid] = target.replace("slides/", "")

        pres_content = zf.read("ppt/presentation.xml").decode("utf-8")
        pres_dom = defusedxml.minidom.parseString(pres_content)

        slides = []
        for sld_id in pres_dom.getElementsByTagName("p:sldId"):
            rid = sld_id.getAttribute("r:id")
            if rid in rid_to_slide:
                hidden = sld_id.getAttribute("show") == "0"
                slides.append({"name": rid_to_slide[rid], "hidden": hidden})

    return slides


def _create_hidden_placeholder(size: tuple[int, int]) -> Image.Image:
    img = Image.new("RGB", size, color="#F0F0F0")
    draw = ImageDraw.Draw(img)
    line_width = max(5, min(size) // 100)
    draw.line([(0, 0), size], fill="#CCCCCC", width=line_width)
    draw.line([(size[0], 0), (0, size[1])], fill="#CCCCCC", width=line_width)
    return img


def _create_thumbnail_grid(
    slides: list[tuple[str, str]],  # (img_path, label)
    cols: int,
    width: int,
    output_path: str,
) -> list[str]:
    """將投影片縮圖排列成格格圖，超出單格上限時分成多張輸出。回傳已寫出的檔案路徑清單。"""
    font_size = int(width * _GRID_FONT_SIZE_RATIO)
    label_padding = int(font_size * _GRID_LABEL_PADDING_RATIO)

    with Image.open(slides[0][0]) as first:
        aspect = first.height / first.width
    thumb_h = int(width * aspect)

    try:
        font = ImageFont.load_default(size=font_size)
    except Exception:
        font = ImageFont.load_default()

    max_per_grid = cols * (cols + 1)
    output_p = Path(output_path)
    grid_files: list[str] = []

    for chunk_idx, start in enumerate(range(0, len(slides), max_per_grid)):
        chunk = slides[start: start + max_per_grid]
        rows = (len(chunk) + cols - 1) // cols
        grid_w = cols * width + (cols + 1) * _GRID_PADDING
        cell_h = thumb_h + font_size + label_padding * 2
        grid_h = rows * cell_h + (rows + 1) * _GRID_PADDING

        grid = Image.new("RGB", (grid_w, grid_h), "white")
        draw = ImageDraw.Draw(grid)

        for i, (img_path, label) in enumerate(chunk):
            row, col = i // cols, i % cols
            x = col * width + (col + 1) * _GRID_PADDING
            y_base = row * cell_h + (row + 1) * _GRID_PADDING

            bbox = draw.textbbox((0, 0), label, font=font)
            text_w = bbox[2] - bbox[0]
            draw.text(
                (x + (width - text_w) // 2, y_base + label_padding),
                label, fill="black", font=font,
            )

            y_thumb = y_base + label_padding + font_size + label_padding
            with Image.open(img_path) as img:
                img.thumbnail((width, thumb_h), Image.Resampling.LANCZOS)
                w, h = img.size
                tx = x + (width - w) // 2
                ty = y_thumb + (thumb_h - h) // 2
                grid.paste(img, (tx, ty))
                if _GRID_BORDER_WIDTH > 0:
                    draw.rectangle(
                        [
                            (tx - _GRID_BORDER_WIDTH, ty - _GRID_BORDER_WIDTH),
                            (tx + w + _GRID_BORDER_WIDTH - 1, ty + h + _GRID_BORDER_WIDTH - 1),
                        ],
                        outline="gray",
                        width=_GRID_BORDER_WIDTH,
                    )

        if len(slides) <= max_per_grid:
            out_file = output_p
        else:
            out_file = output_p.parent / f"{output_p.stem}-{chunk_idx + 1}{output_p.suffix}"

        out_file.parent.mkdir(parents=True, exist_ok=True)
        grid.save(str(out_file), quality=_GRID_JPEG_QUALITY)
        grid_files.append(str(out_file))

    return grid_files


@mcp.tool()
async def capture_ppt_slides(
    ppt_path: str = Field(description="PPT/PPTX 檔案路徑。支援：對話資料夾（如 'uploads/slides.pptx'、'artifacts/report.ppt'）、系統技能資源（如 'system_skills/pptgenjs/assets/templates/auo.pptx'）、使用者技能資源（如 'skills/mypptskill/template.pptx'）"),
    slides: list[int] = Field(
        default=[],
        description=(
            "要注入 LLM 上下文的投影片編號列表（從 1 開始）。\n"
            "留空（[]）表示只轉換存檔，不注入任何頁（適合先取得頁數清單再決定要看哪幾頁）。\n"
            "例如 [1, 3, 5] 表示只將第 1、3、5 張注入上下文。\n"
            "注意：所有投影片都會轉換並儲存到 artifacts/，summary 會列出完整路徑清單。\n"
            "grid=True 時此參數被忽略，改為注入 grid 縮圖圖。"
        )
    ),
    grid: bool = Field(
        default=False,
        description=(
            "是否產生縮圖格格圖（grid）。\n"
            "True：將所有投影片縮圖排列成格格圖，注入 LLM 上下文（slides 參數忽略）。\n"
            "False：依照 slides 參數注入個別頁。"
        )
    ),
    grid_cols: int = Field(
        default=3,
        description=f"grid 模式的每列欄數（預設 3，最大 {_GRID_MAX_COLS}）。",
    ),
) -> str:
    """使用 soffice（LibreOffice）將 PPT/PPTX 轉為 PDF，再用 pymupdf 逐頁轉 PNG 儲存至 artifacts/。
    .pptx 檔案會解析 XML 取得正確投影片順序與隱藏狀態；隱藏投影片以灰底斜線佔位圖呈現。
    指定頁的圖片自動注入 LLM 上下文；summary 列出全部已生成路徑，後續看其他頁直接用 read_file 即可。

    回傳格式為 JSON：{"__image_files__": {slide_num_or_grid_key: abs_path}, "summary": "..."}
    """
    import fitz  # pymupdf

    soffice = shutil.which("soffice") or shutil.which("soffice.bin")
    if not soffice:
        return "錯誤：找不到 soffice（LibreOffice），請確認系統已安裝 LibreOffice 並加入 PATH。"

    ctx_data = _session_ctx.get()
    user_id = ctx_data["user_id"]
    root_folder = get_conversation_folder()
    artifacts_dir = get_conversation_artifacts_dir(root_folder)

    ppt_abs = _resolve_user_path(ppt_path, user_id, root_folder)
    allowed_roots = [
        os.path.realpath(root_folder),
        os.path.realpath(os.path.join(_PROJECT_ROOT, "system_skills")),
    ]
    if user_id:
        allowed_roots.append(os.path.realpath(get_user_profile_dir(user_id)))
    if not _check_path_in_allowed_roots(ppt_abs, allowed_roots):
        return "存取拒絕：只能存取對話資料夾、system_skills/ 或自己的技能資料夾中的 PPT 檔案。"

    if not os.path.isfile(ppt_abs):
        return f"PPT 檔案不存在：{ppt_path}"

    ext = os.path.splitext(ppt_abs)[1].lower()
    if ext not in (".ppt", ".pptx", ".odp"):
        return f"不支援的檔案格式：{ext}，請提供 .ppt、.pptx 或 .odp 檔案。"

    cols = min(max(grid_cols, 1), _GRID_MAX_COLS)

    os.makedirs(artifacts_dir, exist_ok=True)
    base_name = os.path.splitext(os.path.basename(ppt_abs))[0]

    tmp_dir = os.path.join(artifacts_dir, f"_ppt_tmp_{base_name}")
    os.makedirs(tmp_dir, exist_ok=True)

    def _run_soffice_pdf():
        cmd = [soffice, "--headless", "--convert-to", "pdf", "--outdir", tmp_dir, ppt_abs]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return proc.returncode, proc.stdout, proc.stderr

    try:
        returncode, stdout, stderr = await asyncio.to_thread(_run_soffice_pdf)
    except subprocess.TimeoutExpired:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return "錯誤：soffice 轉換逾時（超過 120 秒）。"
    except Exception as e:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return f"錯誤：執行 soffice 時發生例外：{str(e)}"

    if returncode != 0:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return f"soffice 轉換失敗（return code {returncode}）：\n{stderr.strip()[-500:]}"

    pdf_path = os.path.join(tmp_dir, f"{base_name}.pdf")
    if not os.path.isfile(pdf_path):
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return f"soffice 執行成功但未找到輸出的 PDF 檔案。\nstdout: {stdout.strip()}\nstderr: {stderr.strip()}"

    # 解析 PPTX XML 取得投影片順序與隱藏狀態（僅限 .pptx）
    slide_info: list[dict] = []
    if ext == ".pptx":
        try:
            slide_info = _get_slide_info(ppt_abs)
        except Exception:
            slide_info = []

    def _render_and_build_slides():
        doc = fitz.open(pdf_path)
        mat = fitz.Matrix(2.0, 2.0)
        render_errors: list[str] = []

        # 轉換 PDF 每頁（對應非隱藏投影片）
        visible_pngs: list[str] = []
        for i in range(doc.page_count):
            dst_name = f"{base_name}_slide_{i + 1:03d}.png"
            dst_abs = os.path.join(artifacts_dir, dst_name)
            try:
                pix = doc[i].get_pixmap(matrix=mat, alpha=False)
                pix.save(dst_abs)
                visible_pngs.append(dst_abs)
            except Exception as e:
                render_errors.append(f"第 {i + 1} 張轉換失敗：{str(e)}")
                visible_pngs.append("")  # 保持索引對齊
        doc.close()

        # 若有 XML 投影片資訊，重新建立含隱藏頁的完整清單
        if slide_info:
            # 重新命名已存在的 PNG，使其對應正確的投影片編號
            visible_iter = iter(p for p in visible_pngs if p)
            all_slide_map: dict[int, str] = {}
            all_slide_labels: dict[int, str] = {}

            for seq, info in enumerate(slide_info, start=1):
                name = info["name"]
                is_hidden = info["hidden"]
                label = f"{name} (hidden)" if is_hidden else name

                if is_hidden:
                    # 用佔位圖取代（以第一張可見圖尺寸為準，若無則預設 1920x1080）
                    ref_path = visible_pngs[0] if visible_pngs and visible_pngs[0] else None
                    if ref_path:
                        with Image.open(ref_path) as ref:
                            placeholder_size = ref.size
                    else:
                        placeholder_size = (1920, 1080)
                    placeholder_img = _create_hidden_placeholder(placeholder_size)
                    ph_name = f"{base_name}_slide_{seq:03d}.png"
                    ph_abs = os.path.join(artifacts_dir, ph_name)
                    placeholder_img.save(ph_abs)
                    all_slide_map[seq] = ph_abs
                else:
                    try:
                        png_path = next(visible_iter)
                        # 若原始檔名不符，重新命名
                        expected_name = f"{base_name}_slide_{seq:03d}.png"
                        expected_abs = os.path.join(artifacts_dir, expected_name)
                        if png_path != expected_abs and os.path.isfile(png_path):
                            os.rename(png_path, expected_abs)
                        all_slide_map[seq] = expected_abs
                    except StopIteration:
                        render_errors.append(f"第 {seq} 張（{name}）無對應 PNG。")
                all_slide_labels[seq] = label
        else:
            # 無 XML 資訊：直接用 fitz 頁順序，重新命名為語意化檔名
            all_slide_map = {}
            all_slide_labels = {}
            for i, png_path in enumerate(visible_pngs):
                seq = i + 1
                if not png_path:
                    continue
                expected_name = f"{base_name}_slide_{seq:03d}.png"
                expected_abs = os.path.join(artifacts_dir, expected_name)
                if png_path != expected_abs and os.path.isfile(png_path):
                    os.rename(png_path, expected_abs)
                all_slide_map[seq] = expected_abs
                all_slide_labels[seq] = f"slide{seq}.xml"

        return all_slide_map, all_slide_labels, render_errors

    try:
        all_slide_map, all_slide_labels, render_errors = await asyncio.to_thread(_render_and_build_slides)
    except Exception as e:
        return f"錯誤：pymupdf 轉換時發生例外：{str(e)}"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    if not all_slide_map:
        return f"轉換失敗，未能產生任何投影片圖片。錯誤：{render_errors}"

    total = len(all_slide_map)
    summary_lines = [
        f"PPT 轉換完成，共 {total} 張投影片，全部已儲存至 artifacts/。",
    ]
    for num, abs_path in sorted(all_slide_map.items()):
        label = all_slide_labels.get(num, "")
        hidden_tag = " [hidden]" if "(hidden)" in label else ""
        summary_lines.append(f"  [{num}] artifacts/{os.path.basename(abs_path)}{hidden_tag}")
    if render_errors:
        summary_lines.extend(render_errors)

    if grid:
        # Grid 模式：合成格格圖，注入 LLM
        grid_slides = [
            (all_slide_map[num], all_slide_labels.get(num, f"slide{num}.xml"))
            for num in sorted(all_slide_map.keys())
            if os.path.isfile(all_slide_map[num])
        ]
        grid_output = os.path.join(artifacts_dir, f"{base_name}_grid.jpg")

        try:
            grid_files = await asyncio.to_thread(
                _create_thumbnail_grid, grid_slides, cols, _GRID_THUMBNAIL_WIDTH, grid_output
            )
        except Exception as e:
            return f"錯誤：產生格格圖時發生例外：{str(e)}"

        summary_lines.append(f"\nGrid 縮圖（{cols} 欄）已產生，共 {len(grid_files)} 張：")
        for gf in grid_files:
            summary_lines.append(f"  artifacts/{os.path.basename(gf)}")

        inject_map = {f"grid_{i + 1}": gf for i, gf in enumerate(grid_files)}
    else:
        # 個別頁注入模式
        if slides:
            inject_map = {str(k): v for k, v in all_slide_map.items() if k in set(slides)}
            missing = sorted(set(slides) - set(all_slide_map.keys()))
            if missing:
                summary_lines.append(f"注意：指定頁 {missing} 超出範圍（共 {total} 張）。")
        else:
            inject_map = {}
        summary_lines.append(
            "若需查看其他頁，直接用 read_file 讀取對應路徑，無需重新轉換。\n"
            f"已注入上下文的頁數：{sorted(int(k) for k in inject_map) if inject_map else '（無）'}"
        )

    return json.dumps({
        "__image_files__": inject_map,
        "summary": "\n".join(summary_lines),
    }, ensure_ascii=False)
