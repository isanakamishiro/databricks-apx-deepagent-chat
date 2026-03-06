"""PDF操作ツール群 for LangGraph Agent.

UC Volume上のPDFファイルを操作するためのLangChainツール群を提供する。
各ツールは内部で「UC Volumeからダウンロード → ローカルで処理 → UC Volumeにアップロード」
のフローを持つ。

すべての処理ロジックはこのファイル内で完結しており、
外部スクリプト (assets/skills/pdf/scripts) への依存はない。
"""

from __future__ import annotations

import json
import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path

from databricks.sdk import WorkspaceClient
from langchain_core.tools import tool as langchain_tool

from .pptx_tools import (
    _download_file,
    _upload_dir,
    _upload_file,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 内部ヘルパー: フォームフィールド情報取得
# ---------------------------------------------------------------------------


def _get_full_annotation_field_id(annotation) -> str | None:
    components = []
    while annotation:
        field_name = annotation.get("/T")
        if field_name:
            components.append(field_name)
        annotation = annotation.get("/Parent")
    return ".".join(reversed(components)) if components else None


def _make_field_dict(field, field_id: str) -> dict:
    field_dict: dict = {"field_id": field_id}
    ft = field.get("/FT")
    if ft == "/Tx":
        field_dict["type"] = "text"
    elif ft == "/Btn":
        field_dict["type"] = "checkbox"
        states = field.get("/_States_", [])
        if len(states) == 2:
            if "/Off" in states:
                field_dict["checked_value"] = (
                    states[0] if states[0] != "/Off" else states[1]
                )
                field_dict["unchecked_value"] = "/Off"
            else:
                field_dict["checked_value"] = states[0]
                field_dict["unchecked_value"] = states[1]
    elif ft == "/Ch":
        field_dict["type"] = "choice"
        states = field.get("/_States_", [])
        field_dict["choice_options"] = [
            {"value": state[0], "text": state[1]} for state in states
        ]
    else:
        field_dict["type"] = f"unknown ({ft})"
    return field_dict


def _get_field_info(reader) -> list[dict]:
    """PdfReaderからフォームフィールド情報を抽出する。"""
    fields = reader.get_fields()
    if not fields:
        return []

    field_info_by_id: dict[str, dict] = {}
    possible_radio_names: set[str] = set()

    for field_id, field in fields.items():
        if field.get("/Kids"):
            if field.get("/FT") == "/Btn":
                possible_radio_names.add(field_id)
            continue
        field_info_by_id[field_id] = _make_field_dict(field, field_id)

    radio_fields_by_id: dict[str, dict] = {}

    for page_index, page in enumerate(reader.pages):
        annotations = page.get("/Annots", [])
        for ann in annotations:
            field_id = _get_full_annotation_field_id(ann)
            if field_id in field_info_by_id:
                field_info_by_id[field_id]["page"] = page_index + 1
                field_info_by_id[field_id]["rect"] = ann.get("/Rect")
            elif field_id in possible_radio_names:
                try:
                    on_values = [v for v in ann["/AP"]["/N"] if v != "/Off"]
                except KeyError:
                    continue
                if len(on_values) == 1:
                    rect = ann.get("/Rect")
                    if field_id not in radio_fields_by_id:
                        radio_fields_by_id[field_id] = {
                            "field_id": field_id,
                            "type": "radio_group",
                            "page": page_index + 1,
                            "radio_options": [],
                        }
                    radio_fields_by_id[field_id]["radio_options"].append(
                        {"value": on_values[0], "rect": rect}
                    )

    fields_with_location = [
        fi for fi in field_info_by_id.values() if "page" in fi
    ]

    def sort_key(f):
        if "radio_options" in f:
            rect = f["radio_options"][0]["rect"] or [0, 0, 0, 0]
        else:
            rect = f.get("rect") or [0, 0, 0, 0]
        adjusted_position = [-rect[1], rect[0]]
        return [f.get("page"), adjusted_position]

    sorted_fields = fields_with_location + list(radio_fields_by_id.values())
    sorted_fields.sort(key=sort_key)
    return sorted_fields


# ---------------------------------------------------------------------------
# 内部ヘルパー: バウンディングボックス検証
# ---------------------------------------------------------------------------


@dataclass
class _RectAndField:
    rect: list[float]
    rect_type: str
    field: dict


def _get_bounding_box_messages(fields_data: dict) -> list[str]:
    messages = []
    messages.append(f"Read {len(fields_data['form_fields'])} fields")

    def rects_intersect(r1, r2):
        disjoint_horizontal = r1[0] >= r2[2] or r1[2] <= r2[0]
        disjoint_vertical = r1[1] >= r2[3] or r1[3] <= r2[1]
        return not (disjoint_horizontal or disjoint_vertical)

    rects_and_fields = []
    for f in fields_data["form_fields"]:
        rects_and_fields.append(_RectAndField(f["label_bounding_box"], "label", f))
        rects_and_fields.append(_RectAndField(f["entry_bounding_box"], "entry", f))

    has_error = False
    for i, ri in enumerate(rects_and_fields):
        for j in range(i + 1, len(rects_and_fields)):
            rj = rects_and_fields[j]
            if ri.field["page_number"] == rj.field["page_number"] and rects_intersect(
                ri.rect, rj.rect
            ):
                has_error = True
                if ri.field is rj.field:
                    messages.append(
                        f"FAILURE: intersection between label and entry bounding boxes "
                        f"for `{ri.field['description']}` ({ri.rect}, {rj.rect})"
                    )
                else:
                    messages.append(
                        f"FAILURE: intersection between {ri.rect_type} bounding box "
                        f"for `{ri.field['description']}` ({ri.rect}) and "
                        f"{rj.rect_type} bounding box for `{rj.field['description']}` ({rj.rect})"
                    )
                if len(messages) >= 20:
                    messages.append(
                        "Aborting further checks; fix bounding boxes and try again"
                    )
                    return messages
        if ri.rect_type == "entry":
            if "entry_text" in ri.field:
                font_size = ri.field["entry_text"].get("font_size", 14)
                entry_height = ri.rect[3] - ri.rect[1]
                if entry_height < font_size:
                    has_error = True
                    messages.append(
                        f"FAILURE: entry bounding box height ({entry_height}) "
                        f"for `{ri.field['description']}` is too short for the text content "
                        f"(font size: {font_size}). Increase the box height or decrease the font size."
                    )
                    if len(messages) >= 20:
                        messages.append(
                            "Aborting further checks; fix bounding boxes and try again"
                        )
                        return messages

    if not has_error:
        messages.append("SUCCESS: All bounding boxes are valid")
    return messages


# ---------------------------------------------------------------------------
# 内部ヘルパー: フォーム記入（アノテーション方式）
# ---------------------------------------------------------------------------


def _transform_from_image_coords(bbox, image_width, image_height, pdf_width, pdf_height):
    x_scale = pdf_width / image_width
    y_scale = pdf_height / image_height
    left = bbox[0] * x_scale
    right = bbox[2] * x_scale
    top = pdf_height - (bbox[1] * y_scale)
    bottom = pdf_height - (bbox[3] * y_scale)
    return left, bottom, right, top


def _transform_from_pdf_coords(bbox, pdf_height):
    left = bbox[0]
    right = bbox[2]
    pypdf_top = pdf_height - bbox[1]
    pypdf_bottom = pdf_height - bbox[3]
    return left, pypdf_bottom, right, pypdf_top


# ---------------------------------------------------------------------------
# 内部ヘルパー: フィラブルフィールド値検証
# ---------------------------------------------------------------------------


def _validation_error_for_field_value(field_info: dict, field_value: str) -> str | None:
    field_type = field_info["type"]
    field_id = field_info["field_id"]
    if field_type == "checkbox":
        checked_val = field_info["checked_value"]
        unchecked_val = field_info["unchecked_value"]
        if field_value != checked_val and field_value != unchecked_val:
            return (
                f'ERROR: Invalid value "{field_value}" for checkbox field "{field_id}". '
                f'The checked value is "{checked_val}" and the unchecked value is "{unchecked_val}"'
            )
    elif field_type == "radio_group":
        option_values = [opt["value"] for opt in field_info["radio_options"]]
        if field_value not in option_values:
            return (
                f'ERROR: Invalid value "{field_value}" for radio group field "{field_id}". '
                f"Valid values are: {option_values}"
            )
    elif field_type == "choice":
        choice_values = [opt["value"] for opt in field_info["choice_options"]]
        if field_value not in choice_values:
            return (
                f'ERROR: Invalid value "{field_value}" for choice field "{field_id}". '
                f"Valid values are: {choice_values}"
            )
    return None


def _monkeypatch_pypdf_method():
    from pypdf.constants import FieldDictionaryAttributes
    from pypdf.generic import DictionaryObject

    original_get_inherited = DictionaryObject.get_inherited

    def patched_get_inherited(self, key: str, default=None):
        result = original_get_inherited(self, key, default)
        if key == FieldDictionaryAttributes.Opt:
            if isinstance(result, list) and all(
                isinstance(v, list) and len(v) == 2 for v in result
            ):
                result = [r[0] for r in result]
        return result

    DictionaryObject.get_inherited = patched_get_inherited  # type: ignore[method-assign]


# ---------------------------------------------------------------------------
# ツールファクトリ
# ---------------------------------------------------------------------------


def create_pdf_tools(
    workspace_client: WorkspaceClient,
    volume_path: str,
) -> list:
    """PDF操作用のLangChainツール群を生成する。

    Args:
        workspace_client: Databricks WorkspaceClient
        volume_path: UC Volumeのルートパス (例: "/Volumes/catalog/schema/volume")

    Returns:
        list of langchain tools
    """
    ws = workspace_client
    vp = volume_path

    @langchain_tool
    def check_fillable_fields(file_path: str) -> str:
        """PDFにフィラブル（入力可能な）フォームフィールドがあるかを確認します。

        Args:
            file_path: UC Volume上のPDFファイルパス (例: "/documents/form.pdf")
        """
        from pypdf import PdfReader

        with tempfile.TemporaryDirectory() as tmp:
            local_pdf = Path(tmp) / "input.pdf"
            _download_file(ws, vp, file_path, local_pdf)
            reader = PdfReader(str(local_pdf))
            if reader.get_fields():
                return "This PDF has fillable form fields"
            return "This PDF does not have fillable form fields; you will need to visually determine where to enter data"

    @langchain_tool
    def extract_form_field_info(file_path: str, output_path: str) -> str:
        """フィラブルPDFのフォームフィールド情報を抽出し、JSON形式でUC Volumeに保存します。

        Args:
            file_path: UC Volume上のPDFファイルパス (例: "/documents/form.pdf")
            output_path: 出力JSONファイルのUC Volumeパス (例: "/documents/field_info.json")
        """
        from pypdf import PdfReader

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            local_pdf = tmp_path / "input.pdf"
            local_json = tmp_path / "field_info.json"

            _download_file(ws, vp, file_path, local_pdf)
            reader = PdfReader(str(local_pdf))
            field_info = _get_field_info(reader)

            local_json.write_text(json.dumps(field_info, indent=2, ensure_ascii=False))
            _upload_file(ws, vp, local_json, output_path)

            return f"{len(field_info)} フィールドを抽出し、'{output_path}' に保存しました。"

    @langchain_tool
    def convert_pdf_to_images(file_path: str, output_dir: str) -> str:
        """PDFの各ページをPNG画像に変換し、UC Volumeにアップロードします。

        Args:
            file_path: UC Volume上のPDFファイルパス (例: "/documents/form.pdf")
            output_dir: 画像出力先のUC Volumeディレクトリパス (例: "/documents/images/")
        """
        from pdf2image import convert_from_path

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            local_pdf = tmp_path / "input.pdf"
            local_images_dir = tmp_path / "images"
            local_images_dir.mkdir()

            _download_file(ws, vp, file_path, local_pdf)
            images = convert_from_path(str(local_pdf), dpi=200)

            max_dim = 1000
            results = []
            for i, image in enumerate(images):
                width, height = image.size
                if width > max_dim or height > max_dim:
                    scale_factor = min(max_dim / width, max_dim / height)
                    new_width = int(width * scale_factor)
                    new_height = int(height * scale_factor)
                    image = image.resize((new_width, new_height))

                image_path = local_images_dir / f"page_{i + 1}.png"
                image.save(str(image_path))
                results.append(f"page_{i + 1}.png (size: {image.size})")

            count = _upload_dir(ws, vp, local_images_dir, output_dir)
            return (
                f"{len(images)} ページをPNG画像に変換し、'{output_dir}' にアップロードしました "
                f"({count} ファイル):\n" + "\n".join(f"  {r}" for r in results)
            )

    @langchain_tool
    def fill_fillable_fields(
        file_path: str, field_values_json: str, output_path: str
    ) -> str:
        """フィラブルPDFのフォームフィールドに値を入力し、結果を保存します。

        Args:
            file_path: UC Volume上の入力PDFファイルパス (例: "/documents/form.pdf")
            field_values_json: UC Volume上のフィールド値JSONファイルパス (例: "/documents/field_values.json")
            output_path: 出力PDFファイルのUC Volumeパス (例: "/documents/filled_form.pdf")
        """
        from pypdf import PdfReader, PdfWriter

        _monkeypatch_pypdf_method()

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            local_pdf = tmp_path / "input.pdf"
            local_json = tmp_path / "field_values.json"
            local_output = tmp_path / "output.pdf"

            _download_file(ws, vp, file_path, local_pdf)
            _download_file(ws, vp, field_values_json, local_json)

            with open(local_json) as f:
                fields = json.load(f)

            fields_by_page: dict[int, dict[str, str]] = {}
            for field in fields:
                if "value" in field:
                    page = field["page"]
                    if page not in fields_by_page:
                        fields_by_page[page] = {}
                    fields_by_page[page][field["field_id"]] = field["value"]

            reader = PdfReader(str(local_pdf))

            # バリデーション
            errors = []
            field_info = _get_field_info(reader)
            fields_by_ids = {f["field_id"]: f for f in field_info}
            for field in fields:
                existing_field = fields_by_ids.get(field["field_id"])
                if not existing_field:
                    errors.append(f"ERROR: `{field['field_id']}` is not a valid field ID")
                elif field["page"] != existing_field["page"]:
                    errors.append(
                        f"ERROR: Incorrect page number for `{field['field_id']}` "
                        f"(got {field['page']}, expected {existing_field['page']})"
                    )
                elif "value" in field:
                    err = _validation_error_for_field_value(
                        existing_field, field["value"]
                    )
                    if err:
                        errors.append(err)

            if errors:
                return "バリデーションエラー:\n" + "\n".join(errors)

            writer = PdfWriter(clone_from=reader)
            for page, field_values in fields_by_page.items():
                writer.update_page_form_field_values(
                    writer.pages[page - 1], field_values, auto_regenerate=False
                )
            writer.set_need_appearances_writer(True)

            with open(local_output, "wb") as f:
                writer.write(f)

            _upload_file(ws, vp, local_output, output_path)
            return f"フォームフィールドに値を入力し、'{output_path}' に保存しました。"

    @langchain_tool
    def extract_form_structure(file_path: str, output_path: str) -> str:
        """非フィラブルPDFのフォーム構造（テキストラベル、線、チェックボックス）を抽出し、JSON形式で保存します。

        Args:
            file_path: UC Volume上のPDFファイルパス (例: "/documents/form.pdf")
            output_path: 出力JSONファイルのUC Volumeパス (例: "/documents/form_structure.json")
        """
        import pdfplumber

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            local_pdf = tmp_path / "input.pdf"
            local_json = tmp_path / "form_structure.json"

            _download_file(ws, vp, file_path, local_pdf)

            structure: dict = {
                "pages": [],
                "labels": [],
                "lines": [],
                "checkboxes": [],
                "row_boundaries": [],
            }

            with pdfplumber.open(str(local_pdf)) as pdf:
                for page_num, page in enumerate(pdf.pages, 1):
                    structure["pages"].append(
                        {
                            "page_number": page_num,
                            "width": float(page.width),
                            "height": float(page.height),
                        }
                    )

                    words = page.extract_words()
                    for word in words:
                        structure["labels"].append(
                            {
                                "page": page_num,
                                "text": word["text"],
                                "x0": round(float(word["x0"]), 1),
                                "top": round(float(word["top"]), 1),
                                "x1": round(float(word["x1"]), 1),
                                "bottom": round(float(word["bottom"]), 1),
                            }
                        )

                    for line in page.lines:
                        if abs(float(line["x1"]) - float(line["x0"])) > page.width * 0.5:
                            structure["lines"].append(
                                {
                                    "page": page_num,
                                    "y": round(float(line["top"]), 1),
                                    "x0": round(float(line["x0"]), 1),
                                    "x1": round(float(line["x1"]), 1),
                                }
                            )

                    for rect in page.rects:
                        width = float(rect["x1"]) - float(rect["x0"])
                        height = float(rect["bottom"]) - float(rect["top"])
                        if 5 <= width <= 15 and 5 <= height <= 15 and abs(width - height) < 2:
                            structure["checkboxes"].append(
                                {
                                    "page": page_num,
                                    "x0": round(float(rect["x0"]), 1),
                                    "top": round(float(rect["top"]), 1),
                                    "x1": round(float(rect["x1"]), 1),
                                    "bottom": round(float(rect["bottom"]), 1),
                                    "center_x": round(
                                        (float(rect["x0"]) + float(rect["x1"])) / 2, 1
                                    ),
                                    "center_y": round(
                                        (float(rect["top"]) + float(rect["bottom"])) / 2, 1
                                    ),
                                }
                            )

            # 行境界の計算
            lines_by_page: dict[int, list[float]] = {}
            for line in structure["lines"]:
                page = line["page"]
                if page not in lines_by_page:
                    lines_by_page[page] = []
                lines_by_page[page].append(line["y"])

            for page, y_coords in lines_by_page.items():
                y_coords = sorted(set(y_coords))
                for i in range(len(y_coords) - 1):
                    structure["row_boundaries"].append(
                        {
                            "page": page,
                            "row_top": y_coords[i],
                            "row_bottom": y_coords[i + 1],
                            "row_height": round(y_coords[i + 1] - y_coords[i], 1),
                        }
                    )

            local_json.write_text(json.dumps(structure, indent=2, ensure_ascii=False))
            _upload_file(ws, vp, local_json, output_path)

            return (
                f"フォーム構造を抽出し、'{output_path}' に保存しました:\n"
                f"  - {len(structure['pages'])} ページ\n"
                f"  - {len(structure['labels'])} テキストラベル\n"
                f"  - {len(structure['lines'])} 水平線\n"
                f"  - {len(structure['checkboxes'])} チェックボックス\n"
                f"  - {len(structure['row_boundaries'])} 行境界"
            )

    @langchain_tool
    def check_bounding_boxes(fields_json_path: str) -> str:
        """fields.jsonのバウンディングボックスを検証し、交差や不適切なサイズがないか確認します。

        Args:
            fields_json_path: UC Volume上のfields.jsonファイルパス (例: "/documents/fields.json")
        """
        with tempfile.TemporaryDirectory() as tmp:
            local_json = Path(tmp) / "fields.json"
            _download_file(ws, vp, fields_json_path, local_json)

            with open(local_json) as f:
                fields_data = json.load(f)

            messages = _get_bounding_box_messages(fields_data)
            return "\n".join(messages)

    @langchain_tool
    def fill_pdf_form_with_annotations(
        file_path: str, fields_json_path: str, output_path: str
    ) -> str:
        """非フィラブルPDFにテキストアノテーションを追加してフォームに記入し、結果を保存します。

        Args:
            file_path: UC Volume上の入力PDFファイルパス (例: "/documents/form.pdf")
            fields_json_path: UC Volume上のfields.jsonファイルパス (例: "/documents/fields.json")
            output_path: 出力PDFファイルのUC Volumeパス (例: "/documents/filled_form.pdf")
        """
        from pypdf import PdfReader, PdfWriter
        from pypdf.annotations import FreeText

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            local_pdf = tmp_path / "input.pdf"
            local_json = tmp_path / "fields.json"
            local_output = tmp_path / "output.pdf"

            _download_file(ws, vp, file_path, local_pdf)
            _download_file(ws, vp, fields_json_path, local_json)

            with open(local_json) as f:
                fields_data = json.load(f)

            reader = PdfReader(str(local_pdf))
            writer = PdfWriter()
            writer.append(reader)

            pdf_dimensions: dict[int, list] = {}
            for i, page in enumerate(reader.pages):
                mediabox = page.mediabox
                pdf_dimensions[i + 1] = [mediabox.width, mediabox.height]

            annotation_count = 0
            for field in fields_data["form_fields"]:
                page_num = field["page_number"]
                page_info = next(
                    p for p in fields_data["pages"] if p["page_number"] == page_num
                )
                pdf_width, pdf_height = pdf_dimensions[page_num]

                if "pdf_width" in page_info:
                    transformed_entry_box = _transform_from_pdf_coords(
                        field["entry_bounding_box"], float(pdf_height)
                    )
                else:
                    image_width = page_info["image_width"]
                    image_height = page_info["image_height"]
                    transformed_entry_box = _transform_from_image_coords(
                        field["entry_bounding_box"],
                        image_width,
                        image_height,
                        float(pdf_width),
                        float(pdf_height),
                    )

                if "entry_text" not in field or "text" not in field["entry_text"]:
                    continue
                entry_text = field["entry_text"]
                text = entry_text["text"]
                if not text:
                    continue

                font_name = entry_text.get("font", "Arial")
                font_size = str(entry_text.get("font_size", 14)) + "pt"
                font_color = entry_text.get("font_color", "000000")

                annotation = FreeText(
                    text=text,
                    rect=transformed_entry_box,
                    font=font_name,
                    font_size=font_size,
                    font_color=font_color,
                    border_color=None,
                    background_color=None,
                )
                writer.add_annotation(page_number=page_num - 1, annotation=annotation)
                annotation_count += 1

            with open(local_output, "wb") as f:
                writer.write(f)

            _upload_file(ws, vp, local_output, output_path)
            return (
                f"PDFフォームにアノテーションを追加し、'{output_path}' に保存しました。"
                f"\n{annotation_count} 個のテキストアノテーションを追加しました。"
            )

    @langchain_tool
    def create_validation_image(
        page_number: int,
        fields_json_path: str,
        input_image_path: str,
        output_image_path: str,
    ) -> str:
        """バウンディングボックスの検証画像を作成します。ラベルは青、入力欄は赤の矩形で表示します。

        Args:
            page_number: 対象ページ番号（1始まり）
            fields_json_path: UC Volume上のfields.jsonファイルパス (例: "/documents/fields.json")
            input_image_path: UC Volume上の入力画像ファイルパス (例: "/documents/images/page_1.png")
            output_image_path: UC Volume上の出力画像ファイルパス (例: "/documents/validation/page_1.png")
        """
        from PIL import Image, ImageDraw

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            local_json = tmp_path / "fields.json"
            local_input = tmp_path / "input.png"
            local_output = tmp_path / "output.png"

            _download_file(ws, vp, fields_json_path, local_json)
            _download_file(ws, vp, input_image_path, local_input)

            with open(local_json) as f:
                data = json.load(f)

            img = Image.open(str(local_input))
            draw = ImageDraw.Draw(img)
            num_boxes = 0

            for field in data["form_fields"]:
                if field["page_number"] == page_number:
                    entry_box = field["entry_bounding_box"]
                    label_box = field["label_bounding_box"]
                    draw.rectangle(entry_box, outline="red", width=2)
                    draw.rectangle(label_box, outline="blue", width=2)
                    num_boxes += 2

            img.save(str(local_output))
            _upload_file(ws, vp, local_output, output_image_path)

            return (
                f"検証画像を作成し、'{output_image_path}' に保存しました。"
                f"\n{num_boxes} 個のバウンディングボックスを描画しました。"
            )

    return [
        check_fillable_fields,
        extract_form_field_info,
        convert_pdf_to_images,
        fill_fillable_fields,
        extract_form_structure,
        check_bounding_boxes,
        fill_pdf_form_with_annotations,
        create_validation_image,
    ]
