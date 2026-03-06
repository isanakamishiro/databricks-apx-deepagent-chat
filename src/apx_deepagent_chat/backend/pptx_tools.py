"""PPTX操作ツール群 for LangGraph Agent.

UC Volume上のPPTXファイルを操作するためのLangChainツール群を提供する。
各ツールは内部で「UC Volumeからダウンロード → ローカルで処理 → UC Volumeにアップロード」
のフローを持つ。

すべての処理ロジックはこのファイル内で完結しており、
外部スクリプト (assets/skills/pptx/scripts) への依存はない。
"""

from __future__ import annotations

import io
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

import defusedxml.minidom
from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound, ResourceDoesNotExist
from langchain_core.tools import tool as langchain_tool
from markitdown import MarkItDown
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# UC Volume ↔ ローカル 同期ヘルパー
# ---------------------------------------------------------------------------


def _to_real_path(volume_path: str, virtual_path: str) -> str:
    vp = virtual_path if virtual_path.startswith("/") else "/" + virtual_path
    result = volume_path.rstrip("/") + vp
    if result.endswith("/") and len(result) > 1:
        result = result.rstrip("/")
    return result


def _download_file(
    ws_client: WorkspaceClient,
    volume_path: str,
    virtual_path: str,
    local_path: Path,
) -> None:
    real_path = _to_real_path(volume_path, virtual_path)
    resp = ws_client.files.download(real_path)
    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_bytes(resp.contents.read())  # type: ignore[union-attr]


def _upload_file(
    ws_client: WorkspaceClient,
    volume_path: str,
    local_path: Path,
    virtual_path: str,
) -> None:
    real_path = _to_real_path(volume_path, virtual_path)
    parent = str(PurePosixPath(real_path).parent)
    try:
        ws_client.files.create_directory(parent)
    except Exception:
        pass
    ws_client.files.upload(real_path, io.BytesIO(local_path.read_bytes()), overwrite=True)


def _download_dir(
    ws_client: WorkspaceClient,
    volume_path: str,
    virtual_dir: str,
    local_dir: Path,
) -> None:
    real_base = _to_real_path(volume_path, virtual_dir)
    stack = [real_base]
    while stack:
        current = stack.pop()
        try:
            entries = list(ws_client.files.list_directory_contents(current))
        except (NotFound, ResourceDoesNotExist):
            continue
        for entry in entries:
            if entry.path is None:
                continue
            if entry.is_directory:
                stack.append(entry.path)
            else:
                rel = entry.path[len(real_base) :].lstrip("/")
                local_file = local_dir / rel
                local_file.parent.mkdir(parents=True, exist_ok=True)
                try:
                    resp = ws_client.files.download(entry.path)
                    local_file.write_bytes(resp.contents.read())  # type: ignore[union-attr]
                except Exception as e:
                    logger.warning("Failed to download %s: %s", entry.path, e)


def _upload_dir(
    ws_client: WorkspaceClient,
    volume_path: str,
    local_dir: Path,
    virtual_dir: str,
) -> int:
    count = 0
    for local_file in local_dir.rglob("*"):
        if not local_file.is_file():
            continue
        rel = local_file.relative_to(local_dir)
        virtual_path = f"{virtual_dir.rstrip('/')}/{rel}"
        _upload_file(ws_client, volume_path, local_file, virtual_path)
        count += 1
    return count


# ---------------------------------------------------------------------------
# Unpack ヘルパー (PPTX用)
# ---------------------------------------------------------------------------

_SMART_QUOTE_REPLACEMENTS = {
    "\u201c": "&#x201C;",
    "\u201d": "&#x201D;",
    "\u2018": "&#x2018;",
    "\u2019": "&#x2019;",
}


def _pretty_print_xml(xml_file: Path) -> None:
    try:
        content = xml_file.read_text(encoding="utf-8")
        dom = defusedxml.minidom.parseString(content)
        xml_file.write_bytes(dom.toprettyxml(indent="  ", encoding="utf-8"))
    except Exception:
        pass


def _escape_smart_quotes(xml_file: Path) -> None:
    try:
        content = xml_file.read_text(encoding="utf-8")
        for char, entity in _SMART_QUOTE_REPLACEMENTS.items():
            content = content.replace(char, entity)
        xml_file.write_text(content, encoding="utf-8")
    except Exception:
        pass


def _unpack_office(
    input_file: str,
    output_directory: str,
) -> tuple[None, str]:
    """Officeファイル (PPTX等) をZIP展開し、XMLを整形する。"""
    input_path = Path(input_file)
    output_path = Path(output_directory)

    if not input_path.exists():
        return None, f"Error: {input_file} does not exist"

    suffix = input_path.suffix.lower()
    if suffix not in {".docx", ".pptx", ".xlsx"}:
        return None, f"Error: {input_file} must be a .docx, .pptx, or .xlsx file"

    try:
        output_path.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(input_path, "r") as zf:
            zf.extractall(output_path)

        xml_files = list(output_path.rglob("*.xml")) + list(output_path.rglob("*.rels"))
        for xml_file in xml_files:
            _pretty_print_xml(xml_file)

        message = f"Unpacked {input_file} ({len(xml_files)} XML files)"

        for xml_file in xml_files:
            _escape_smart_quotes(xml_file)

        return None, message

    except zipfile.BadZipFile:
        return None, f"Error: {input_file} is not a valid Office file"
    except Exception as e:
        return None, f"Error unpacking: {e}"


# ---------------------------------------------------------------------------
# Pack ヘルパー
# ---------------------------------------------------------------------------


def _condense_xml(xml_file: Path) -> None:
    """XMLを圧縮形式に変換する (pretty-printの逆操作)。"""
    try:
        with open(xml_file, encoding="utf-8") as f:
            dom = defusedxml.minidom.parse(f)

        for element in dom.getElementsByTagName("*"):
            if element.tagName.endswith(":t"):
                continue
            for child in list(element.childNodes):
                if (
                    child.nodeType == child.TEXT_NODE
                    and child.nodeValue
                    and child.nodeValue.strip() == ""
                ) or child.nodeType == child.COMMENT_NODE:
                    element.removeChild(child)

        xml_file.write_bytes(dom.toxml(encoding="UTF-8"))
    except Exception as e:
        logger.error("Failed to condense %s: %s", xml_file.name, e)
        raise


def _pack_office(
    input_directory: str,
    output_file: str,
) -> tuple[None, str]:
    """アンパック済みディレクトリをOfficeファイル (PPTX等) に再パックする。"""
    input_dir = Path(input_directory)
    output_path = Path(output_file)
    suffix = output_path.suffix.lower()

    if not input_dir.is_dir():
        return None, f"Error: {input_dir} is not a directory"

    if suffix not in {".docx", ".pptx", ".xlsx"}:
        return None, f"Error: {output_file} must be a .docx, .pptx, or .xlsx file"

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_content_dir = Path(temp_dir) / "content"
        shutil.copytree(input_dir, temp_content_dir)

        for pattern in ["*.xml", "*.rels"]:
            for xml_file in temp_content_dir.rglob(pattern):
                _condense_xml(xml_file)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in temp_content_dir.rglob("*"):
                if f.is_file() and f.suffix != ".bak":
                    zf.write(f, f.relative_to(temp_content_dir))

    return None, f"Successfully packed {input_dir} to {output_file}"


# ---------------------------------------------------------------------------
# Add Slide ヘルパー
# ---------------------------------------------------------------------------


def _get_next_slide_number(slides_dir: Path) -> int:
    existing = [
        int(m.group(1))
        for f in slides_dir.glob("slide*.xml")
        if (m := re.match(r"slide(\d+)\.xml", f.name))
    ]
    return max(existing) + 1 if existing else 1


def _add_to_content_types(unpacked_dir: Path, dest: str) -> None:
    content_types_path = unpacked_dir / "[Content_Types].xml"
    content_types = content_types_path.read_text(encoding="utf-8")

    new_override = (
        f'<Override PartName="/ppt/slides/{dest}" '
        f'ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'
    )

    if f"/ppt/slides/{dest}" not in content_types:
        content_types = content_types.replace("</Types>", f"  {new_override}\n</Types>")
        content_types_path.write_text(content_types, encoding="utf-8")


def _add_to_presentation_rels(unpacked_dir: Path, dest: str) -> str:
    pres_rels_path = unpacked_dir / "ppt" / "_rels" / "presentation.xml.rels"
    pres_rels = pres_rels_path.read_text(encoding="utf-8")

    rids = [int(m) for m in re.findall(r'Id="rId(\d+)"', pres_rels)]
    next_rid = max(rids) + 1 if rids else 1
    rid = f"rId{next_rid}"

    new_rel = (
        f'<Relationship Id="{rid}" '
        f'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" '
        f'Target="slides/{dest}"/>'
    )

    if f"slides/{dest}" not in pres_rels:
        pres_rels = pres_rels.replace("</Relationships>", f"  {new_rel}\n</Relationships>")
        pres_rels_path.write_text(pres_rels, encoding="utf-8")

    return rid


def _get_next_slide_id(unpacked_dir: Path) -> int:
    pres_path = unpacked_dir / "ppt" / "presentation.xml"
    pres_content = pres_path.read_text(encoding="utf-8")
    slide_ids = [int(m) for m in re.findall(r'<p:sldId[^>]*id="(\d+)"', pres_content)]
    return max(slide_ids) + 1 if slide_ids else 256


def _parse_slide_source(source: str) -> tuple[str, str | None]:
    if source.startswith("slideLayout") and source.endswith(".xml"):
        return ("layout", source)
    return ("slide", None)


def _create_slide_from_layout(unpacked_dir: Path, layout_file: str) -> dict:
    slides_dir = unpacked_dir / "ppt" / "slides"
    rels_dir = slides_dir / "_rels"
    layouts_dir = unpacked_dir / "ppt" / "slideLayouts"

    layout_path = layouts_dir / layout_file
    if not layout_path.exists():
        raise FileNotFoundError(f"{layout_path} not found")

    next_num = _get_next_slide_number(slides_dir)
    dest = f"slide{next_num}.xml"
    dest_slide = slides_dir / dest
    dest_rels = rels_dir / f"{dest}.rels"

    slide_xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld>
    <p:spTree>
      <p:nvGrpSpPr>
        <p:cNvPr id="1" name=""/>
        <p:cNvGrpSpPr/>
        <p:nvPr/>
      </p:nvGrpSpPr>
      <p:grpSpPr>
        <a:xfrm>
          <a:off x="0" y="0"/>
          <a:ext cx="0" cy="0"/>
          <a:chOff x="0" y="0"/>
          <a:chExt cx="0" cy="0"/>
        </a:xfrm>
      </p:grpSpPr>
    </p:spTree>
  </p:cSld>
  <p:clrMapOvr>
    <a:masterClrMapping/>
  </p:clrMapOvr>
</p:sld>'''
    dest_slide.write_text(slide_xml, encoding="utf-8")

    rels_dir.mkdir(exist_ok=True)
    rels_xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/{layout_file}"/>
</Relationships>'''
    dest_rels.write_text(rels_xml, encoding="utf-8")

    _add_to_content_types(unpacked_dir, dest)
    rid = _add_to_presentation_rels(unpacked_dir, dest)
    next_slide_id = _get_next_slide_id(unpacked_dir)
    sld_id_xml = f'<p:sldId id="{next_slide_id}" r:id="{rid}"/>'

    return {
        "dest": dest,
        "slide_id": next_slide_id,
        "rid": rid,
        "sld_id_xml": sld_id_xml,
        "message": f"Created {dest} from {layout_file}. Add to presentation.xml <p:sldIdLst>: {sld_id_xml}",
    }


def _duplicate_slide(unpacked_dir: Path, source: str) -> dict:
    slides_dir = unpacked_dir / "ppt" / "slides"
    rels_dir = slides_dir / "_rels"

    source_slide = slides_dir / source
    if not source_slide.exists():
        raise FileNotFoundError(f"{source_slide} not found")

    next_num = _get_next_slide_number(slides_dir)
    dest = f"slide{next_num}.xml"
    dest_slide = slides_dir / dest

    source_rels = rels_dir / f"{source}.rels"
    dest_rels = rels_dir / f"{dest}.rels"

    shutil.copy2(source_slide, dest_slide)

    if source_rels.exists():
        shutil.copy2(source_rels, dest_rels)
        rels_content = dest_rels.read_text(encoding="utf-8")
        rels_content = re.sub(
            r'\s*<Relationship[^>]*Type="[^"]*notesSlide"[^>]*/>\s*',
            "\n",
            rels_content,
        )
        dest_rels.write_text(rels_content, encoding="utf-8")

    _add_to_content_types(unpacked_dir, dest)
    rid = _add_to_presentation_rels(unpacked_dir, dest)
    next_slide_id = _get_next_slide_id(unpacked_dir)
    sld_id_xml = f'<p:sldId id="{next_slide_id}" r:id="{rid}"/>'

    return {
        "dest": dest,
        "slide_id": next_slide_id,
        "rid": rid,
        "sld_id_xml": sld_id_xml,
        "message": f"Created {dest} from {source}. Add to presentation.xml <p:sldIdLst>: {sld_id_xml}",
    }


def _add_slide(unpacked_dir: str, source: str) -> dict:
    """スライドを追加する (複製またはレイアウトから新規作成)。"""
    unpacked = Path(unpacked_dir)
    if not unpacked.exists():
        raise FileNotFoundError(f"{unpacked_dir} not found")

    source_type, layout_file = _parse_slide_source(source)

    if source_type == "layout" and layout_file is not None:
        return _create_slide_from_layout(unpacked, layout_file)
    else:
        return _duplicate_slide(unpacked, source)


# ---------------------------------------------------------------------------
# Clean ヘルパー
# ---------------------------------------------------------------------------


def _get_slides_in_sldidlst(unpacked_dir: Path) -> set[str]:
    pres_path = unpacked_dir / "ppt" / "presentation.xml"
    pres_rels_path = unpacked_dir / "ppt" / "_rels" / "presentation.xml.rels"

    if not pres_path.exists() or not pres_rels_path.exists():
        return set()

    rels_dom = defusedxml.minidom.parse(str(pres_rels_path))
    rid_to_slide = {}
    for rel in rels_dom.getElementsByTagName("Relationship"):
        rid = rel.getAttribute("Id")
        target = rel.getAttribute("Target")
        rel_type = rel.getAttribute("Type")
        if "slide" in rel_type and target.startswith("slides/"):
            rid_to_slide[rid] = target.replace("slides/", "")

    pres_content = pres_path.read_text(encoding="utf-8")
    referenced_rids = set(re.findall(r'<p:sldId[^>]*r:id="([^"]+)"', pres_content))

    return {rid_to_slide[rid] for rid in referenced_rids if rid in rid_to_slide}


def _remove_orphaned_slides(unpacked_dir: Path) -> list[str]:
    slides_dir = unpacked_dir / "ppt" / "slides"
    slides_rels_dir = slides_dir / "_rels"
    pres_rels_path = unpacked_dir / "ppt" / "_rels" / "presentation.xml.rels"

    if not slides_dir.exists():
        return []

    referenced_slides = _get_slides_in_sldidlst(unpacked_dir)
    removed = []

    for slide_file in slides_dir.glob("slide*.xml"):
        if slide_file.name not in referenced_slides:
            rel_path = slide_file.relative_to(unpacked_dir)
            slide_file.unlink()
            removed.append(str(rel_path))

            rels_file = slides_rels_dir / f"{slide_file.name}.rels"
            if rels_file.exists():
                rels_file.unlink()
                removed.append(str(rels_file.relative_to(unpacked_dir)))

    if removed and pres_rels_path.exists():
        rels_dom = defusedxml.minidom.parse(str(pres_rels_path))
        changed = False

        for rel in list(rels_dom.getElementsByTagName("Relationship")):
            target = rel.getAttribute("Target")
            if target.startswith("slides/"):
                slide_name = target.replace("slides/", "")
                if slide_name not in referenced_slides:
                    if rel.parentNode:
                        rel.parentNode.removeChild(rel)
                        changed = True

        if changed:
            with open(pres_rels_path, "wb") as f:
                f.write(rels_dom.toxml(encoding="utf-8"))

    return removed


def _remove_trash_directory(unpacked_dir: Path) -> list[str]:
    trash_dir = unpacked_dir / "[trash]"
    removed = []

    if trash_dir.exists() and trash_dir.is_dir():
        for file_path in trash_dir.iterdir():
            if file_path.is_file():
                rel_path = file_path.relative_to(unpacked_dir)
                removed.append(str(rel_path))
                file_path.unlink()
        trash_dir.rmdir()

    return removed


def _get_slide_referenced_files(unpacked_dir: Path) -> set:
    referenced = set()
    slides_rels_dir = unpacked_dir / "ppt" / "slides" / "_rels"

    if not slides_rels_dir.exists():
        return referenced

    for rels_file in slides_rels_dir.glob("*.rels"):
        dom = defusedxml.minidom.parse(str(rels_file))
        for rel in dom.getElementsByTagName("Relationship"):
            target = rel.getAttribute("Target")
            if not target:
                continue
            target_path = (rels_file.parent.parent / target).resolve()
            try:
                referenced.add(target_path.relative_to(unpacked_dir.resolve()))
            except ValueError:
                pass

    return referenced


def _remove_orphaned_rels_files(unpacked_dir: Path) -> list[str]:
    resource_dirs = ["charts", "diagrams", "drawings"]
    removed = []
    slide_referenced = _get_slide_referenced_files(unpacked_dir)

    for dir_name in resource_dirs:
        rels_dir = unpacked_dir / "ppt" / dir_name / "_rels"
        if not rels_dir.exists():
            continue

        for rels_file in rels_dir.glob("*.rels"):
            resource_file = rels_dir.parent / rels_file.name.replace(".rels", "")
            try:
                resource_rel_path = resource_file.resolve().relative_to(unpacked_dir.resolve())
            except ValueError:
                continue

            if not resource_file.exists() or resource_rel_path not in slide_referenced:
                rels_file.unlink()
                rel_path = rels_file.relative_to(unpacked_dir)
                removed.append(str(rel_path))

    return removed


def _get_referenced_files(unpacked_dir: Path) -> set:
    referenced = set()

    for rels_file in unpacked_dir.rglob("*.rels"):
        dom = defusedxml.minidom.parse(str(rels_file))
        for rel in dom.getElementsByTagName("Relationship"):
            target = rel.getAttribute("Target")
            if not target:
                continue
            target_path = (rels_file.parent.parent / target).resolve()
            try:
                referenced.add(target_path.relative_to(unpacked_dir.resolve()))
            except ValueError:
                pass

    return referenced


def _remove_orphaned_files(unpacked_dir: Path, referenced: set) -> list[str]:
    resource_dirs = ["media", "embeddings", "charts", "diagrams", "tags", "drawings", "ink"]
    removed = []

    for dir_name in resource_dirs:
        dir_path = unpacked_dir / "ppt" / dir_name
        if not dir_path.exists():
            continue

        for file_path in dir_path.glob("*"):
            if not file_path.is_file():
                continue
            rel_path = file_path.relative_to(unpacked_dir)
            if rel_path not in referenced:
                file_path.unlink()
                removed.append(str(rel_path))

    theme_dir = unpacked_dir / "ppt" / "theme"
    if theme_dir.exists():
        for file_path in theme_dir.glob("theme*.xml"):
            rel_path = file_path.relative_to(unpacked_dir)
            if rel_path not in referenced:
                file_path.unlink()
                removed.append(str(rel_path))
                theme_rels = theme_dir / "_rels" / f"{file_path.name}.rels"
                if theme_rels.exists():
                    theme_rels.unlink()
                    removed.append(str(theme_rels.relative_to(unpacked_dir)))

    notes_dir = unpacked_dir / "ppt" / "notesSlides"
    if notes_dir.exists():
        for file_path in notes_dir.glob("*.xml"):
            if not file_path.is_file():
                continue
            rel_path = file_path.relative_to(unpacked_dir)
            if rel_path not in referenced:
                file_path.unlink()
                removed.append(str(rel_path))

        notes_rels_dir = notes_dir / "_rels"
        if notes_rels_dir.exists():
            for file_path in notes_rels_dir.glob("*.rels"):
                notes_file = notes_dir / file_path.name.replace(".rels", "")
                if not notes_file.exists():
                    file_path.unlink()
                    removed.append(str(file_path.relative_to(unpacked_dir)))

    return removed


def _update_content_types(unpacked_dir: Path, removed_files: list[str]) -> None:
    ct_path = unpacked_dir / "[Content_Types].xml"
    if not ct_path.exists():
        return

    dom = defusedxml.minidom.parse(str(ct_path))
    changed = False

    for override in list(dom.getElementsByTagName("Override")):
        part_name = override.getAttribute("PartName").lstrip("/")
        if part_name in removed_files:
            if override.parentNode:
                override.parentNode.removeChild(override)
                changed = True

    if changed:
        with open(ct_path, "wb") as f:
            f.write(dom.toxml(encoding="utf-8"))


def _clean_unused_files(unpacked_dir: Path) -> list[str]:
    """アンパック済みPPTXから孤立ファイルを削除する。"""
    all_removed = []

    slides_removed = _remove_orphaned_slides(unpacked_dir)
    all_removed.extend(slides_removed)

    trash_removed = _remove_trash_directory(unpacked_dir)
    all_removed.extend(trash_removed)

    while True:
        removed_rels = _remove_orphaned_rels_files(unpacked_dir)
        referenced = _get_referenced_files(unpacked_dir)
        removed_files = _remove_orphaned_files(unpacked_dir, referenced)

        total_removed = removed_rels + removed_files
        if not total_removed:
            break

        all_removed.extend(total_removed)

    if all_removed:
        _update_content_types(unpacked_dir, all_removed)

    return all_removed


# ---------------------------------------------------------------------------
# Translation ヘルパー (translate_pptx.py からインライン移植)
# ---------------------------------------------------------------------------


def _is_japanese(text: str) -> bool:
    """日本語文字 (ひらがな・カタカナ・漢字・全角) を含むか判定する。"""
    for ch in text:
        cp = ord(ch)
        if (
            0x3040 <= cp <= 0x309F  # Hiragana
            or 0x30A0 <= cp <= 0x30FF  # Katakana
            or 0x4E00 <= cp <= 0x9FFF  # CJK Unified
            or 0x3400 <= cp <= 0x4DBF  # CJK Extension A
            or 0xFF01 <= cp <= 0xFF60  # Fullwidth forms
        ):
            return True
    return False


def _xml_escape(text: str) -> str:
    """XML <a:t> 要素に安全に挿入できるようエスケープする。"""
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    text = text.replace("\u2018", "&#x2018;")
    text = text.replace("\u2019", "&#x2019;")
    text = text.replace("\u201C", "&#x201C;")
    text = text.replace("\u201D", "&#x201D;")
    return text


def _get_slide_paths(work_dir: Path) -> list[tuple[int, Path]]:
    """スライドXMLパス一覧を (スライド番号, パス) のソート済みリストで返す。"""
    slides_dir = work_dir / "ppt" / "slides"
    if not slides_dir.is_dir():
        return []
    result = []
    for f in slides_dir.iterdir():
        m = re.match(r"^slide(\d+)\.xml$", f.name)
        if m:
            result.append((int(m.group(1)), f))
    result.sort(key=lambda x: x[0])
    return result


def _extract_texts_from_slide(slide_path: Path) -> tuple[list[str], list[dict]]:
    """スライドXMLから日本語テキストとパラグラフコンテキストを抽出する。"""
    content = slide_path.read_text(encoding="utf-8")

    try:
        dom = defusedxml.minidom.parseString(content.encode("utf-8"))
    except Exception as e:
        logger.warning("XML parse error in %s: %s", slide_path, e)
        return [], []

    ns_a = "http://schemas.openxmlformats.org/drawingml/2006/main"

    all_texts: list[str] = []
    t_elements = dom.getElementsByTagNameNS(ns_a, "t")
    for t_el in t_elements:
        text = ""
        for child in t_el.childNodes:
            if child.nodeType == child.TEXT_NODE:
                text += child.data
        if text and _is_japanese(text):
            if text not in all_texts:
                all_texts.append(text)

    paragraphs: list[dict] = []
    p_elements = dom.getElementsByTagNameNS(ns_a, "p")
    for p_el in p_elements:
        runs: list[str] = []
        r_elements = p_el.getElementsByTagNameNS(ns_a, "r")
        for r_el in r_elements:
            t_els = r_el.getElementsByTagNameNS(ns_a, "t")
            for t_el in t_els:
                text = ""
                for child in t_el.childNodes:
                    if child.nodeType == child.TEXT_NODE:
                        text += child.data
                if text:
                    runs.append(text)
        if len(runs) > 1:
            combined = "".join(runs)
            if _is_japanese(combined):
                paragraphs.append({"runs": runs, "combined": combined})

    return all_texts, paragraphs


def _apply_dict_to_slide(slide_path: Path, trans_dict: dict[str, str]) -> int:
    """翻訳辞書をスライドXMLに適用する。置換数を返す。"""
    content = slide_path.read_text(encoding="utf-8")

    bak_path = Path(str(slide_path) + ".bak")
    if not bak_path.exists():
        shutil.copy2(slide_path, bak_path)

    sorted_keys = sorted(trans_dict.keys(), key=len, reverse=True)

    count = 0
    for ja_text in sorted_keys:
        en_text = trans_dict[ja_text]  # type: ignore[index]
        escaped_en = _xml_escape(en_text)
        escaped_ja_for_regex = re.escape(ja_text)  # type: ignore[arg-type]

        pattern = r"(<a:t(?:\s[^>]*)?>)" + escaped_ja_for_regex + r"(</a:t>)"
        replacement = r"\g<1>" + escaped_en.replace("\\", "\\\\") + r"\g<2>"

        new_content, n = re.subn(pattern, replacement, content)
        if n > 0:
            count += n
            content = new_content

    if count > 0:
        slide_path.write_text(content, encoding="utf-8")

    return count


def _estimate_display_width(text: str) -> int:
    """テキスト表示幅を推定する。日本語文字は半角2文字分。"""
    width = 0
    for ch in text:
        cp = ord(ch)
        if (
            0x3040 <= cp <= 0x309F
            or 0x30A0 <= cp <= 0x30FF
            or 0x4E00 <= cp <= 0x9FFF
            or 0x3400 <= cp <= 0x4DBF
            or 0xFF01 <= cp <= 0xFF60
        ):
            width += 2
        else:
            width += 1
    return width


def _get_textbox_info(slide_path: Path) -> list[dict]:
    """スライドXMLからテキストボックス情報 (名前・サイズ・テキスト) を抽出する。"""
    content = slide_path.read_text(encoding="utf-8")

    try:
        dom = defusedxml.minidom.parseString(content.encode("utf-8"))
    except Exception:
        return []

    ns_a = "http://schemas.openxmlformats.org/drawingml/2006/main"
    ns_p = "http://schemas.openxmlformats.org/presentationml/2006/main"

    results = []
    sp_elements = dom.getElementsByTagNameNS(ns_p, "sp")

    for sp in sp_elements:
        nv_elements = sp.getElementsByTagNameNS(ns_p, "nvSpPr")
        name = ""
        if nv_elements:
            for child in nv_elements[0].childNodes:
                if child.nodeType == child.ELEMENT_NODE and child.localName == "cNvPr":
                    name = child.getAttribute("name")
                    break

        ext_elements = sp.getElementsByTagNameNS(ns_a, "ext")
        cx, cy = 0, 0
        if ext_elements:
            cx_str = ext_elements[0].getAttribute("cx")
            cy_str = ext_elements[0].getAttribute("cy")
            cx = int(cx_str) if cx_str else 0
            cy = int(cy_str) if cy_str else 0

        t_elements = sp.getElementsByTagNameNS(ns_a, "t")
        texts = []
        for t_el in t_elements:
            text = ""
            for child in t_el.childNodes:
                if child.nodeType == child.TEXT_NODE:
                    text += child.data
            if text.strip():
                texts.append(text)

        if texts:
            combined = "".join(texts)
            results.append({
                "name": name,
                "cx": cx,
                "cy": cy,
                "texts": texts,
                "combined": combined,
            })

    return results


def _parse_slides_filter(slides: str | None) -> set[int] | None:
    """スライド番号フィルタ文字列 ("1,2,3" or "1-5") をパースする。"""
    if not slides:
        return None
    result: set[int] = set()
    for part in slides.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-", 1)
            for i in range(int(start), int(end) + 1):
                result.add(i)
        else:
            result.add(int(part))
    return result


# ---------------------------------------------------------------------------
# ツールファクトリ
# ---------------------------------------------------------------------------


def create_pptx_tools(
    workspace_client: WorkspaceClient,
    volume_path: str,
) -> list:
    """PPTX操作用のLangChainツール群を生成する。

    Args:
        workspace_client: Databricks WorkspaceClient
        volume_path: UC Volumeのルートパス (例: "/Volumes/catalog/schema/volume")

    Returns:
        list of langchain tools
    """
    ws = workspace_client
    vp = volume_path

    @langchain_tool
    def unpack_pptx(file_path: str, output_dir: str) -> str:
        """PPTXファイルをアンパック（展開）します。テンプレートの分析や編集の前準備に使用します。

        Args:
            file_path: UC Volume上のPPTXファイルパス (例: "/presentations/template.pptx")
            output_dir: 展開先のディレクトリパス (例: "/presentations/unpacked/")
        """
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            local_pptx = tmp_path / "input.pptx"
            local_output = tmp_path / "unpacked"

            _download_file(ws, vp, file_path, local_pptx)
            _, message = _unpack_office(str(local_pptx), str(local_output))

            if "Error" in message:
                return f"エラー: {message}"

            count = _upload_dir(ws, vp, local_output, output_dir)
            return f"{message}。{count} ファイルをUC Volume '{output_dir}' にアップロードしました。"

    @langchain_tool
    def pack_pptx(input_dir: str, output_path: str) -> str:
        """アンパック済みディレクトリをPPTXファイルに再パックします。編集完了後のPPTX生成に使用します。

        Args:
            input_dir: UC Volume上のアンパック済みディレクトリパス (例: "/presentations/unpacked/")
            output_path: 出力PPTXファイルパス (例: "/presentations/output.pptx")
        """
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            local_input = tmp_path / "unpacked"
            local_output = tmp_path / "output.pptx"

            _download_dir(ws, vp, input_dir, local_input)

            _, message = _pack_office(
                str(local_input),
                str(local_output),
            )

            if "Error" in message:
                return f"エラー: {message}"

            _upload_file(ws, vp, local_output, output_path)
            return f"{message}。UC Volume '{output_path}' にアップロードしました。"

    @langchain_tool
    def add_pptx_slide(unpacked_dir: str, source: str) -> str:
        """アンパック済みPPTXディレクトリにスライドを追加（複製またはレイアウトから作成）します。

        Args:
            unpacked_dir: UC Volume上のアンパック済みディレクトリパス (例: "/presentations/unpacked/")
            source: スライドファイル名 (例: "slide2.xml") で複製、またはレイアウトファイル名 (例: "slideLayout2.xml") で新規作成
        """
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            local_dir = tmp_path / "unpacked"

            _download_dir(ws, vp, unpacked_dir, local_dir)

            result = _add_slide(str(local_dir), source)

            _upload_dir(ws, vp, local_dir, unpacked_dir)
            return result["message"]

    @langchain_tool
    def clean_pptx(unpacked_dir: str) -> str:
        """アンパック済みPPTXディレクトリから孤立ファイル（不要なスライド、メディア、リレーション）を削除します。

        Args:
            unpacked_dir: UC Volume上のアンパック済みディレクトリパス (例: "/presentations/unpacked/")
        """
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            local_dir = tmp_path / "unpacked"

            _download_dir(ws, vp, unpacked_dir, local_dir)

            removed = _clean_unused_files(local_dir)

            _upload_dir(ws, vp, local_dir, unpacked_dir)

            if removed:
                return f"{len(removed)} 個の孤立ファイルを削除しました:\n" + "\n".join(f"  {f}" for f in removed)
            return "孤立ファイルは見つかりませんでした。"

    @langchain_tool
    def pptx_to_markdown(file_path: str) -> str:
        """PPTXファイルをMarkdown形式のテキストに変換します。
        テンプレートのプレースホルダテキストやスライド構成の確認に使用します。

        Args:
            file_path: UC Volume上のPPTXファイルパス (例: "/presentations/template.pptx")
        """
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            local_pptx = tmp_path / "input.pptx"

            _download_file(ws, vp, file_path, local_pptx)

            md = MarkItDown()
            result = md.convert(str(local_pptx))
            return result.text_content

    @langchain_tool
    def create_pptx_from_js(js_code: str, output_path: str) -> str:
        """PptxGenJSのJavaScriptコードを実行してPPTXファイルを生成します。
        テンプレートなしでゼロからプレゼンテーションを作成する場合に使用します。

        Args:
            js_code: PptxGenJSを使用したJavaScriptコード。
                     pres.writeFile({ fileName: "output.pptx" }) で終了すること。
            output_path: UC Volume上の出力PPTXファイルパス (例: "/presentations/output.pptx")
        """
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)

            # package.json を生成
            package_json = {
                "name": "pptx-gen",
                "private": True,
                "dependencies": {
                    "pptxgenjs": "latest",
                    "react-icons": "latest",
                    "react": "latest",
                    "react-dom": "latest",
                    "sharp": "latest",
                },
            }
            (tmp_path / "package.json").write_text(json.dumps(package_json))

            # npm install
            result = subprocess.run(
                ["npm", "install", "--prefer-offline"],
                cwd=str(tmp_path),
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                return f"エラー: npm install に失敗: {result.stderr}"

            # JSコード内の writeFile パスを一時ディレクトリに書き換え
            local_pptx = tmp_path / "output.pptx"
            modified_code = re.sub(
                r'writeFile\(\s*\{[^}]*fileName\s*:\s*["\'][^"\']+["\']',
                f'writeFile({{ fileName: "{local_pptx}"',
                js_code,
            )

            # スクリプト書き出し・実行
            script_path = tmp_path / "generate.js"
            script_path.write_text(modified_code, encoding="utf-8")

            result = subprocess.run(
                ["node", str(script_path)],
                cwd=str(tmp_path),
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                return f"エラー: スクリプト実行に失敗: {result.stderr}"

            # 生成されたPPTXを探してアップロード
            pptx_files = list(tmp_path.glob("*.pptx"))
            if not pptx_files:
                return "エラー: PPTXファイルが生成されませんでした。"

            _upload_file(ws, vp, pptx_files[0], output_path)
            return f"PPTXを生成し、UC Volume '{output_path}' にアップロードしました。"

    @langchain_tool
    def extract_pptx_texts(unpacked_dir: str, output_dir: str) -> str:
        """アンパック済みPPTXからスライドごとの日本語テキストをJSON形式で抽出します。
        翻訳ワークフローの最初のステップとして使用します。

        Args:
            unpacked_dir: UC Volume上のアンパック済みディレクトリパス (例: "/presentations/unpacked/")
            output_dir: 抽出結果JSON出力先ディレクトリパス (例: "/presentations/texts/")
        """
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            local_dir = tmp_path / "unpacked"
            local_output = tmp_path / "texts"
            local_output.mkdir(parents=True, exist_ok=True)

            _download_dir(ws, vp, unpacked_dir, local_dir)

            slide_paths = _get_slide_paths(local_dir)
            if not slide_paths:
                return "エラー: スライドXMLファイルが見つかりません。"

            total_texts = 0
            files_created = 0
            summary_lines = []

            for slide_num, slide_path in slide_paths:
                texts, paragraphs = _extract_texts_from_slide(slide_path)
                if not texts and not paragraphs:
                    continue

                data = {
                    "slide": slide_num,
                    "texts": texts,
                    "paragraphs": paragraphs,
                }

                out_path = local_output / f"slide{slide_num}.json"
                out_path.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

                total_texts += len(texts)
                files_created += 1
                summary_lines.append(
                    f"  slide{slide_num}.json: {len(texts)} texts, {len(paragraphs)} multi-run paragraphs"
                )

            _upload_dir(ws, vp, local_output, output_dir)

            summary = f"{total_texts} 件の日本語テキストを {files_created} スライドから抽出しました。\n"
            summary += f"出力先: {output_dir}\n"
            summary += "\n".join(summary_lines)
            return summary

    @langchain_tool
    def apply_pptx_translation(unpacked_dir: str, dict_path: str, slides: str = "") -> str:
        """翻訳辞書JSONをアンパック済みPPTXのスライドXMLに適用します。
        辞書のキーは元の<a:t>テキスト、値は翻訳後テキストです。

        Args:
            unpacked_dir: UC Volume上のアンパック済みディレクトリパス (例: "/presentations/unpacked/")
            dict_path: UC Volume上の翻訳辞書JSONファイルパス (例: "/presentations/dict_slide1.json")
            slides: 対象スライド番号 (例: "1,2,3" or "1-5")。空文字の場合は全スライド対象。
        """
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            local_dir = tmp_path / "unpacked"
            local_dict = tmp_path / "dict.json"

            _download_dir(ws, vp, unpacked_dir, local_dir)
            _download_file(ws, vp, dict_path, local_dict)

            trans_dict = json.loads(local_dict.read_text(encoding="utf-8"))
            if not trans_dict:
                return "警告: 翻訳辞書が空です。"

            slides_filter = _parse_slides_filter(slides if slides else None)
            slide_paths = _get_slide_paths(local_dir)
            total_replacements = 0
            summary_lines = []

            for slide_num, slide_path in slide_paths:
                if slides_filter and slide_num not in slides_filter:
                    continue
                count = _apply_dict_to_slide(slide_path, trans_dict)
                if count > 0:
                    summary_lines.append(f"  slide{slide_num}.xml: {count} replacements")
                    total_replacements += count
                else:
                    summary_lines.append(f"  slide{slide_num}.xml: no matches")

            _upload_dir(ws, vp, local_dir, unpacked_dir)

            summary = f"合計 {total_replacements} 件の置換を実行しました。\n"
            summary += "\n".join(summary_lines)
            return summary

    @langchain_tool
    def verify_pptx_translation(unpacked_dir: str) -> str:
        """アンパック済みPPTXのXMLバリデーションと残存日本語テキストのチェックを行います。

        Args:
            unpacked_dir: UC Volume上のアンパック済みディレクトリパス (例: "/presentations/unpacked/")
        """
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            local_dir = tmp_path / "unpacked"

            _download_dir(ws, vp, unpacked_dir, local_dir)

            slide_paths = _get_slide_paths(local_dir)
            if not slide_paths:
                return "エラー: スライドXMLファイルが見つかりません。"

            xml_errors: list[tuple[int, str]] = []
            remaining_japanese: list[tuple[int, str]] = []

            for slide_num, slide_path in slide_paths:
                content = slide_path.read_text(encoding="utf-8")

                try:
                    dom = defusedxml.minidom.parseString(content.encode("utf-8"))
                except Exception as e:
                    xml_errors.append((slide_num, str(e)))
                    continue

                ns_a = "http://schemas.openxmlformats.org/drawingml/2006/main"
                t_elements = dom.getElementsByTagNameNS(ns_a, "t")

                for t_el in t_elements:
                    text = ""
                    for child in t_el.childNodes:
                        if child.nodeType == child.TEXT_NODE:
                            text += child.data
                    if text and _is_japanese(text):
                        remaining_japanese.append((slide_num, text.strip() or text))

            lines = ["=== Verification Results ==="]

            if xml_errors:
                lines.append(f"\nXML ERRORS: {len(xml_errors)}")
                for slide_num, err in xml_errors:
                    lines.append(f"  slide{slide_num}: {err}")
            else:
                lines.append("\nXML validity: OK (all slides parse successfully)")

            if remaining_japanese:
                lines.append(f"\nRemaining Japanese text: {len(remaining_japanese)} items")
                for slide_num, text in remaining_japanese:
                    display = text[:60] + "..." if len(text) > 60 else text
                    lines.append(f"  slide{slide_num}: {display}")
            else:
                lines.append("\nRemaining Japanese: NONE (all translated)")

            if xml_errors:
                lines.append("\n*** RESULT: NG (XML errors found) ***")
            elif remaining_japanese:
                lines.append(f"\n*** RESULT: WARNING ({len(remaining_japanese)} Japanese texts remain) ***")
            else:
                lines.append("\n*** RESULT: OK ***")

            return "\n".join(lines)

    @langchain_tool
    def check_pptx_layout(unpacked_dir: str) -> str:
        """アンパック済みPPTXで翻訳後のテキストオーバーフローリスクを検出します。
        .bakファイル（翻訳前のバックアップ）と比較して幅の増加率を判定します。

        Args:
            unpacked_dir: UC Volume上のアンパック済みディレクトリパス (例: "/presentations/unpacked/")
        """
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            local_dir = tmp_path / "unpacked"

            _download_dir(ws, vp, unpacked_dir, local_dir)

            slide_paths = _get_slide_paths(local_dir)
            if not slide_paths:
                return "エラー: スライドXMLファイルが見つかりません。"

            warnings_count = 0
            criticals_count = 0
            lines = ["=== Layout Check Results ===\n"]

            for slide_num, slide_path in slide_paths:
                bak_path = Path(str(slide_path) + ".bak")
                if not bak_path.exists():
                    continue

                orig_boxes = _get_textbox_info(bak_path)
                new_boxes = _get_textbox_info(slide_path)

                if len(orig_boxes) != len(new_boxes):
                    continue

                for orig, new in zip(orig_boxes, new_boxes):
                    orig_width = _estimate_display_width(orig["combined"])
                    new_width = _estimate_display_width(new["combined"])

                    if orig_width == 0:
                        continue

                    ratio = new_width / orig_width

                    is_small = orig["cx"] > 0 and orig["cx"] < 2743200
                    warn_threshold = 1.2 if is_small else 1.3
                    crit_threshold = 1.4 if is_small else 1.6

                    level = None
                    if ratio >= crit_threshold:
                        level = "CRITICAL"
                        criticals_count += 1
                    elif ratio >= warn_threshold:
                        level = "WARNING"
                        warnings_count += 1

                    if level:
                        name = orig["name"] or "(unnamed)"
                        orig_text = orig["combined"][:40] + "..." if len(orig["combined"]) > 40 else orig["combined"]
                        new_text = new["combined"][:40] + "..." if len(new["combined"]) > 40 else new["combined"]
                        lines.append(f"  [{level}] slide{slide_num} / {name}")
                        lines.append(f"    Original: {orig_text}")
                        lines.append(f"    Translated: {new_text}")
                        lines.append(f"    Width ratio: {ratio:.2f}x")
                        lines.append("")

            lines.append(f"Summary: {criticals_count} CRITICAL, {warnings_count} WARNING")
            if criticals_count > 0:
                lines.append("*** Consider shortening CRITICAL translations ***")

            return "\n".join(lines)

    return [
        unpack_pptx,
        pack_pptx,
        add_pptx_slide,
        clean_pptx,
        pptx_to_markdown,
        create_pptx_from_js,
        extract_pptx_texts,
        apply_pptx_translation,
        verify_pptx_translation,
        check_pptx_layout,
    ]
