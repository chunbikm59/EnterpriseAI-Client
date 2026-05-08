"""
PPTX 模板套用工具。

保留 template 的 slideMasters/、slideLayouts/、theme/，
將 source（pptxgenjs 生成）的 slides/ 替換進去，重新打包輸出。
"""
import io
import shutil
import tempfile
import zipfile
from pathlib import Path

from lxml import etree

SLIDE_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.presentationml.slide+xml"
)
SLIDE_REL_TYPE = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide"
)
RELS_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CT_NS   = "http://schemas.openxmlformats.org/package/2006/content-types"
P_NS    = "http://schemas.openxmlformats.org/presentationml/2006/main"
R_NS    = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def apply_pptx_template(source_bytes: bytes, template_path: str, layout_hints: list | None = None) -> bytes:
    """將 source_bytes（pptxgenjs 生成的 PPTX）的投影片套用到 template_path 的企業模板中。

    保留模板的 slideMasters/、slideLayouts/、theme/，用 source 的 slides/ 替換。
    layout_hints 為每張投影片的 layout name（對應模板 slideLayout 的 name 屬性），None 表示自動判斷。
    回傳合併後的 PPTX bytes。
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        src_dir = tmp_path / "source"
        tpl_dir = tmp_path / "template"

        with zipfile.ZipFile(io.BytesIO(source_bytes)) as z:
            z.extractall(src_dir)
        with zipfile.ZipFile(template_path) as z:
            z.extractall(tpl_dir)

        _merge_slides(src_dir, tpl_dir, layout_hints or [])

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
            for f in sorted(tpl_dir.rglob("*")):
                if f.is_file():
                    zout.write(f, f.relative_to(tpl_dir))
        return buf.getvalue()


def _merge_slides(src_dir: Path, tpl_dir: Path, layout_hints: list | None = None) -> None:
    """核心合併邏輯，直接修改 tpl_dir 內容。

    layout_hints 為每張投影片的 layout name（對應模板 slideLayout 的 name 屬性）。
    None 或空字串表示該頁自動依位置判斷。
    """
    hints = layout_hints or []
    print(f"[_merge_slides] hints={hints}")
    src_slides_dir = src_dir / "ppt" / "slides"
    tpl_slides_dir = tpl_dir / "ppt" / "slides"
    tpl_rels_dir   = tpl_slides_dir / "_rels"
    tpl_slides_dir.mkdir(parents=True, exist_ok=True)
    tpl_rels_dir.mkdir(parents=True, exist_ok=True)

    # 刪除 template 原有的 slides
    for f in list(tpl_slides_dir.glob("slide*.xml")):
        f.unlink()
    for f in list(tpl_rels_dir.glob("slide*.xml.rels")):
        f.unlink()

    # 掃描模板 layout，key 為 name（精確）與 "type:<ooxml_type>"（fallback）
    layout_map = _scan_template_layouts(tpl_dir)
    print(f"[_merge_slides] layout_map keys={list(layout_map.keys())}")

    # 複製 source slides（重編號從 1 開始）
    src_slides = sorted(
        src_slides_dir.glob("slide*.xml"),
        key=lambda p: int("".join(filter(str.isdigit, p.stem)) or "0"),
    )
    total = len(src_slides)
    for i, src_slide in enumerate(src_slides, 1):
        shutil.copy(src_slide, tpl_slides_dir / f"slide{i}.xml")
        src_rel = src_slides_dir / "_rels" / f"{src_slide.name}.rels"

        hint = hints[i - 1] if i - 1 < len(hints) else None
        if hint and hint in layout_map:
            # 名稱精確匹配
            layout_target = layout_map[hint]
        elif hint and f"type:{hint}" in layout_map:
            # 使用者傳了 OOXML type 字串作為 hint（fallback）
            layout_target = layout_map[f"type:{hint}"]
        elif i == 1 or i == total:
            # 第一張與最後一張：優先 title
            layout_target = (layout_map.get("type:title")
                             or layout_map.get("type:blank")
                             or layout_map.get("type:obj"))
        else:
            # 中間頁：優先 blank/obj
            layout_target = (layout_map.get("type:blank")
                             or layout_map.get("type:obj")
                             or layout_map.get("type:title"))
        print(f"[_merge_slides] slide{i}: hint={hint!r} -> layout_target={layout_target}")

        if src_rel.exists():
            _fix_slide_rels(src_rel, tpl_rels_dir / f"slide{i}.xml.rels", layout_target)

    # 複製 source 的 media（圖片等），不覆蓋 template 已有檔案
    src_media = src_dir / "ppt" / "media"
    tpl_media = tpl_dir / "ppt" / "media"
    if src_media.exists():
        tpl_media.mkdir(exist_ok=True)
        for mf in src_media.iterdir():
            dest = tpl_media / mf.name
            if not dest.exists():
                shutil.copy(mf, dest)

    # 清除孤立的 notesSlides（備忘稿內容，對應已刪除的模板投影片）
    # notesMasters 保留，否則 presentation.xml 的 notesSz 定義會找不到參照而報損壞
    notes_dir = tpl_dir / "ppt" / "notesSlides"
    if notes_dir.exists():
        shutil.rmtree(notes_dir)

    _update_content_types(tpl_dir, len(src_slides))
    _update_presentation(tpl_dir, len(src_slides))


def _scan_template_layouts(tpl_dir: Path) -> dict[str, str]:
    """掃描模板的 slideLayouts，回傳兩種 key 的對應表：

    - name（精確）：layout 的 p:cSld name 屬性，如 "Ending Page"
    - "type:<ooxml_type>"（fallback）：如 "type:title"、"type:blank"

    Target 為 slide rels 中可直接使用的相對路徑（../slideLayouts/slideLayoutN.xml）。
    同一 name 或 type 有多個 layout 時，保留編號最小的。
    """
    import re
    layouts_dir = tpl_dir / "ppt" / "slideLayouts"
    result: dict[str, str] = {}
    if not layouts_dir.exists():
        return result
    for lf in sorted(layouts_dir.glob("slideLayout*.xml"),
                     key=lambda p: int("".join(filter(str.isdigit, p.stem)) or "0")):
        try:
            content = lf.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        target = f"../slideLayouts/{lf.name}"
        # 提取 name（精確 key）
        m_name = re.search(r'<p:cSld[^>]*\bname="([^"]*)"', content)
        if m_name:
            name = m_name.group(1)
            if name and name not in result:
                result[name] = target
        # 提取 OOXML type（fallback key，加 "type:" 前綴避免與 name 衝突）
        m_type = re.search(r'\btype="([^"]+)"', content)
        if m_type:
            type_key = f"type:{m_type.group(1)}"
            if type_key not in result:
                result[type_key] = target
    # 確保 fallback 始終存在
    if not result:
        result["type:title"] = "../slideLayouts/slideLayout1.xml"
    return result


def _fix_slide_rels(src_rels_path: Path, dest_path: Path, layout_target: str | None = None) -> None:
    """複製 slide rels，將 slideLayout 引用改為指定的 layout_target。

    同時移除 notesSlide 引用（模板通常沒有對應的 notesSlide 檔案）。
    layout_target 為 None 時 fallback 至 slideLayout1.xml。
    """
    target = layout_target or "../slideLayouts/slideLayout1.xml"
    tree = etree.parse(str(src_rels_path))
    root = tree.getroot()
    to_remove = []
    for rel in root.findall(f"{{{RELS_NS}}}Relationship"):
        rel_type = rel.get("Type", "")
        if "slideLayout" in rel_type:
            rel.set("Target", target)
        elif "notesSlide" in rel_type:
            to_remove.append(rel)
    for rel in to_remove:
        root.remove(rel)
    tree.write(str(dest_path), xml_declaration=True, encoding="UTF-8", standalone=True)


def _update_content_types(tpl_dir: Path, slide_count: int) -> None:
    ct_path = tpl_dir / "[Content_Types].xml"
    tree = etree.parse(str(ct_path))
    root = tree.getroot()
    # 移除舊 slide 與 notesSlide 條目
    for ov in list(root.findall(f"{{{CT_NS}}}Override")):
        part = ov.get("PartName", "")
        if part.startswith("/ppt/slides/slide") or part.startswith("/ppt/notesSlides/"):
            root.remove(ov)
    # 新增新 slide 條目
    for i in range(1, slide_count + 1):
        ov = etree.SubElement(root, f"{{{CT_NS}}}Override")
        ov.set("PartName", f"/ppt/slides/slide{i}.xml")
        ov.set("ContentType", SLIDE_CONTENT_TYPE)
    tree.write(str(ct_path), xml_declaration=True, encoding="UTF-8", standalone=True)


def _update_presentation(tpl_dir: Path, slide_count: int) -> None:
    pres_path = tpl_dir / "ppt" / "presentation.xml"
    rels_path = tpl_dir / "ppt" / "_rels" / "presentation.xml.rels"

    pres = etree.parse(str(pres_path))
    rels = etree.parse(str(rels_path))
    pres_root = pres.getroot()
    rels_root = rels.getroot()

    # 移除舊 slide relationships
    for rel in list(rels_root):
        if rel.get("Type", "").endswith("/slide"):
            rels_root.remove(rel)

    # 找最大 rId 編號
    max_rid = 0
    for rel in rels_root:
        rid = rel.get("Id", "")
        if rid.startswith("rId"):
            try:
                max_rid = max(max_rid, int(rid[3:]))
            except ValueError:
                pass

    # 清空並重建 sldIdLst
    sld_id_lst = pres_root.find(f"{{{P_NS}}}sldIdLst")
    if sld_id_lst is None:
        sld_id_lst = etree.SubElement(pres_root, f"{{{P_NS}}}sldIdLst")
    for child in list(sld_id_lst):
        sld_id_lst.remove(child)

    # slide id 從 256 起，OOXML 規範上限為 2^31-1，sldMasterId 通常很大不應作為基準
    max_sld_id = 255

    # 新增 slide 條目
    for i in range(1, slide_count + 1):
        max_rid += 1
        max_sld_id += 1
        rid = f"rId{max_rid}"

        sld_el = etree.SubElement(sld_id_lst, f"{{{P_NS}}}sldId")
        sld_el.set("id", str(max_sld_id))
        sld_el.set(f"{{{R_NS}}}id", rid)

        rel_el = etree.SubElement(rels_root, f"{{{RELS_NS}}}Relationship")
        rel_el.set("Id", rid)
        rel_el.set("Type", SLIDE_REL_TYPE)
        rel_el.set("Target", f"slides/slide{i}.xml")

    pres.write(str(pres_path), xml_declaration=True, encoding="UTF-8", standalone=True)
    rels.write(str(rels_path), xml_declaration=True, encoding="UTF-8", standalone=True)
