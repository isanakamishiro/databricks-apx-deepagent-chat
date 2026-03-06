"""DOCX操作ツール群 for LangGraph Agent.

UC Volume上のDOCXファイルを操作するためのLangChainツール群を提供する。
各ツールは内部で「UC Volumeからダウンロード → ローカルで処理 → UC Volumeにアップロード」
のフローを持つ。

すべての処理ロジックはこのファイル内で完結しており、
外部スクリプト (assets/skills/docx/scripts) への依存はない。
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import tempfile
from pathlib import Path

from databricks.sdk import WorkspaceClient
from langchain_core.tools import tool as langchain_tool
from markitdown import MarkItDown

from .pptx_tools import _download_file, _upload_file

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ツールファクトリ
# ---------------------------------------------------------------------------


def create_docx_tools(
    workspace_client: WorkspaceClient,
    volume_path: str,
) -> list:
    """DOCX操作用のLangChainツール群を生成する。

    Args:
        workspace_client: Databricks WorkspaceClient
        volume_path: UC Volumeのルートパス (例: "/Volumes/catalog/schema/volume")

    Returns:
        list of langchain tools
    """
    ws = workspace_client
    vp = volume_path

    @langchain_tool
    def docx_to_markdown(file_path: str) -> str:
        """DOCXファイルをMarkdown形式のテキストに変換します。
        文書の内容確認やテキスト抽出に使用します。

        Args:
            file_path: UC Volume上のDOCXファイルパス (例: "/documents/report.docx")
        """
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            local_docx = tmp_path / "input.docx"

            _download_file(ws, vp, file_path, local_docx)

            md = MarkItDown()
            result = md.convert(str(local_docx))
            return result.text_content

    @langchain_tool
    def create_docx_from_js(js_code: str, output_path: str) -> str:
        """docx-jsのJavaScriptコードを実行してDOCXファイルを生成します。
        テンプレートなしでゼロからWord文書を作成する場合に使用します。

        Args:
            js_code: docx-jsを使用したJavaScriptコード。
                     Packer.toBuffer(doc).then(buffer => fs.writeFileSync("output.docx", buffer)) で終了すること。
            output_path: UC Volume上の出力DOCXファイルパス (例: "/documents/output.docx")
        """
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)

            # package.json を生成
            package_json = {
                "name": "docx-gen",
                "private": True,
                "dependencies": {
                    "docx": "latest",
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

            # JSコード内の writeFileSync パスを一時ディレクトリに書き換え
            local_docx = tmp_path / "output.docx"
            modified_code = re.sub(
                r'writeFileSync\(\s*["\'][^"\']+["\']',
                f'writeFileSync("{local_docx}"',
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

            # 生成されたDOCXを探してアップロード
            docx_files = list(tmp_path.glob("*.docx"))
            if not docx_files:
                return "エラー: DOCXファイルが生成されませんでした。"

            _upload_file(ws, vp, docx_files[0], output_path)
            return f"DOCXを生成し、UC Volume '{output_path}' にアップロードしました。"

    return [docx_to_markdown, create_docx_from_js]
