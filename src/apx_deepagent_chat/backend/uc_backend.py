"""Databricks Unity Catalog Volumes を使った DeepAgents バックエンド.

Databricks SDK の Files API 経由で Unity Catalog Volumes 上のファイル操作を行う.
FUSE マウントが使えない環境向け.
"""

from __future__ import annotations

import fnmatch
import io
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import PurePosixPath
from typing import Any

from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import DatabricksError, NotFound, ResourceDoesNotExist
from deepagents.backends.protocol import (
    BackendProtocol,
    EditResult,
    FileDownloadResponse,
    FileInfo,
    FileUploadResponse,
    GrepMatch,
    WriteResult,
)
from deepagents.backends.utils import (
    check_empty_content,
    format_content_with_line_numbers,
    perform_string_replacement,
)

from .agent_utils import to_real_path, to_virtual_path

logger = logging.getLogger(__name__)

_GREP_MAX_MATCHES = 10000
_GREP_MAX_WORKERS = 8


def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    """glob パターンを正規表現に変換する. *, ?, ** をサポート."""
    i, n = 0, len(pattern)
    parts: list[str] = []
    while i < n:
        c = pattern[i]
        if c == "*":
            if i + 1 < n and pattern[i + 1] == "*":
                # ** は / を含む任意のパスにマッチ
                i += 2
                if i < n and pattern[i] == "/":
                    i += 1
                parts.append(".*")
            else:
                # * は / 以外の任意の文字列にマッチ
                parts.append("[^/]*")
                i += 1
        elif c == "?":
            parts.append("[^/]")
            i += 1
        else:
            parts.append(re.escape(c))
            i += 1
    return re.compile("^" + "".join(parts) + "$")


class UCVolumesBackend(BackendProtocol):
    """Databricks Unity Catalog Volumes を使った DeepAgents バックエンド.

    Databricks SDK の Files API を使用して、Unity Catalog Volumes 上で
    ファイルの読み書き・検索を行う.

    Args:
        volume_path: Volume のルートパス (例: "/Volumes/catalog/schema/volume").
        workspace_client: Databricks WorkspaceClient インスタンス.
            None の場合はデフォルト認証で自動生成.

    Usage:
        ```python
        from databricks.sdk import WorkspaceClient
        from agent_server.uc_backend import UCVolumesBackend

        w = WorkspaceClient()
        backend = UCVolumesBackend(
            volume_path="/Volumes/my_catalog/my_schema/my_volume",
            workspace_client=w,
        )
        ```
    """

    def __init__(
        self,
        volume_path: str,
        workspace_client: WorkspaceClient | None = None,
    ) -> None:
        self.volume_path = volume_path.rstrip("/")
        self._w = workspace_client or WorkspaceClient()

    @property
    def files(self):
        """Databricks Files API クライアント."""
        return self._w.files

    def _real(self, virtual_path: str) -> str:
        """仮想パスを Volumes 上の実パスに変換する."""
        return to_real_path(self.volume_path, virtual_path)

    def _virtual(self, real_path: str) -> str:
        """実パスを仮想パスに変換する."""
        return to_virtual_path(self.volume_path, real_path)

    def _file_exists(self, real_path: str) -> bool:
        """ファイルが存在するか確認する."""
        try:
            self.files.get_metadata(real_path)
            return True
        except (NotFound, ResourceDoesNotExist):
            return False
        except DatabricksError as e:
            logger.warning("_file_exists failed for %s: %s", real_path, e)
            return False

    def _download_text(self, real_path: str) -> str | None:
        """ファイルをダウンロードしてテキストとして返す. 存在しない場合は None."""
        try:
            resp = self.files.download(real_path)
            return resp.contents.read().decode("utf-8")
        except (NotFound, ResourceDoesNotExist):
            return None
        except DatabricksError as e:
            logger.warning("_download_text failed for %s: %s", real_path, e)
            return None

    # --- ファイル走査ヘルパー ---

    def _list_all_files(self, real_path: str) -> list[dict[str, Any]]:
        """ディレクトリを再帰的に走査し、全ファイルのメタデータを返す.

        Returns:
            各要素は real_path, virtual_path, file_size, last_modified を持つ dict.
        """
        results: list[dict[str, Any]] = []
        stack = [real_path]
        while stack:
            current = stack.pop()
            try:
                entries = list(self.files.list_directory_contents(current))
            except (NotFound, ResourceDoesNotExist):
                continue
            except DatabricksError as e:
                logger.warning("_list_all_files failed for %s: %s", current, e)
                continue
            for entry in entries:
                if entry.path is None:
                    continue
                # .checkpointer 等のドットで始まるフォルダ・ファイルを除外する
                basename = PurePosixPath(entry.path).name
                if basename.startswith("."):
                    continue
                if entry.is_directory:
                    stack.append(entry.path)
                else:
                    results.append(
                        {
                            "real_path": entry.path,
                            "virtual_path": self._virtual(entry.path),
                            "file_size": entry.file_size,
                            "last_modified": entry.last_modified,
                        }
                    )
        return results

    # --- BackendProtocol 実装 ---

    def ls_info(self, path: str) -> list[FileInfo]:
        """ディレクトリ直下のファイル・ディレクトリ一覧を返す."""
        real_path = self._real(path)
        infos: list[FileInfo] = []

        try:
            entries = list(self.files.list_directory_contents(real_path))
        except (NotFound, ResourceDoesNotExist):
            return []
        except DatabricksError as e:
            logger.warning("ls_info failed for %s: %s", real_path, e)
            return []

        for entry in entries:
            entry_path = entry.path
            if entry_path is None:
                continue
            # .checkpointer 等のドットで始まるフォルダ・ファイルを除外する
            if PurePosixPath(entry_path).name.startswith("."):
                continue
            virtual = self._virtual(entry_path)
            is_dir = entry.is_directory or False

            info: FileInfo = {
                "path": virtual + "/" if is_dir else virtual,
                "is_dir": is_dir,
            }
            if not is_dir and entry.file_size is not None:
                info["size"] = int(entry.file_size)
            if entry.last_modified is not None:
                info["modified_at"] = str(entry.last_modified)

            infos.append(info)

        infos.sort(key=lambda x: x.get("path", ""))
        return infos

    def read(
        self,
        file_path: str,
        offset: int = 0,
        limit: int = 2000,
    ) -> str:
        """ファイルを行番号付きで読み取る."""
        real_path = self._real(file_path)
        content = self._download_text(real_path)

        if content is None:
            return f"Error: File '{file_path}' not found"

        empty_msg = check_empty_content(content)
        if empty_msg:
            return empty_msg

        lines = content.splitlines()
        start_idx = offset
        end_idx = min(start_idx + limit, len(lines))

        if start_idx >= len(lines):
            return (
                f"Error: Line offset {offset} exceeds file length ({len(lines)} lines)"
            )

        selected_lines = lines[start_idx:end_idx]
        return format_content_with_line_numbers(
            selected_lines, start_line=start_idx + 1
        )

    def write(
        self,
        file_path: str,
        content: str,
    ) -> WriteResult:
        """新規ファイルを作成する. 既存ファイルがある場合はエラー."""
        real_path = self._real(file_path)

        if self._file_exists(real_path):
            return WriteResult(
                error=f"Cannot write to {file_path} because it already exists. "
                "Read and then make an edit, or write to a new path."
            )

        # 親ディレクトリを作成
        parent = str(PurePosixPath(real_path).parent)
        if parent != real_path:
            try:
                self.files.create_directory(parent)
            except Exception:
                pass  # 既に存在する場合は無視

        content_bytes = content.encode("utf-8")
        self.files.upload(real_path, io.BytesIO(content_bytes), overwrite=False)
        return WriteResult(path=file_path, files_update=None)

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        """ファイル内の文字列を置換する."""
        real_path = self._real(file_path)
        content = self._download_text(real_path)

        if content is None:
            return EditResult(error=f"Error: File '{file_path}' not found")

        result = perform_string_replacement(
            content, old_string, new_string, replace_all
        )

        if isinstance(result, str):
            return EditResult(error=result)

        new_content, occurrences = result
        content_bytes = new_content.encode("utf-8")
        self.files.upload(real_path, io.BytesIO(content_bytes), overwrite=True)
        return EditResult(
            path=file_path, files_update=None, occurrences=int(occurrences)
        )

    def grep_raw(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
    ) -> list[GrepMatch] | str:
        """Files API でファイルをダウンロードし、パターンに一致する行を検索する.

        再帰的にファイルを列挙し、ThreadPoolExecutor で並列ダウンロード・検索を行う.

        Args:
            pattern: 検索する文字列 (リテラルマッチ).
            path: 検索対象ディレクトリの仮想パス. None の場合はルート.
            glob: ファイル名の glob パターン (例: "*.py").
        """
        search_path = path or "/"
        real_base = self._real(search_path)

        try:
            all_files = self._list_all_files(real_base)
        except Exception as e:
            return f"Error listing files: {e}"

        # ファイル名フィルタ
        if glob:
            all_files = [
                f
                for f in all_files
                if fnmatch.fnmatch(PurePosixPath(f["virtual_path"]).name, glob)
            ]

        matches: list[GrepMatch] = []

        def _search(file_info: dict[str, Any]) -> list[GrepMatch]:
            content = self._download_text(file_info["real_path"])
            if content is None:
                return []
            found: list[GrepMatch] = []
            for i, line in enumerate(content.splitlines(), 1):
                if pattern in line:
                    found.append(
                        {"path": file_info["virtual_path"], "line": i, "text": line}
                    )
            return found

        with ThreadPoolExecutor(max_workers=_GREP_MAX_WORKERS) as pool:
            for result in pool.map(_search, all_files):
                matches.extend(result)
                if len(matches) >= _GREP_MAX_MATCHES:
                    matches = matches[:_GREP_MAX_MATCHES]
                    break

        matches.sort(key=lambda m: (m["path"], m["line"]))
        return matches

    def glob_info(self, pattern: str, path: str = "/") -> list[FileInfo]:
        """Files API でディレクトリを再帰走査し、glob パターンに一致するファイルを返す.

        Args:
            pattern: glob パターン (例: "*.py", "**/*.txt").
            path: 検索の基点となる仮想パス. デフォルトは "/".
        """
        real_base = self._real(path)

        try:
            all_files = self._list_all_files(real_base)
        except Exception:
            return []

        glob_re = _glob_to_regex(pattern)
        infos: list[FileInfo] = []

        for f in all_files:
            # Volume ルートからの相対パスでマッチ
            rel = f["virtual_path"].lstrip("/")
            if glob_re.search(rel):
                info: FileInfo = {"path": f["virtual_path"], "is_dir": False}
                if f["file_size"] is not None:
                    info["size"] = int(f["file_size"])
                if f["last_modified"] is not None:
                    info["modified_at"] = str(f["last_modified"])
                infos.append(info)

        return infos

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        """複数ファイルを Volume にアップロードする."""
        responses: list[FileUploadResponse] = []

        for virtual_path, content in files:
            real_path = self._real(virtual_path)
            try:
                # 親ディレクトリを作成
                parent = str(PurePosixPath(real_path).parent)
                if parent != real_path:
                    try:
                        self.files.create_directory(parent)
                    except Exception:
                        pass
                self.files.upload(real_path, io.BytesIO(content), overwrite=True)
                responses.append(FileUploadResponse(path=virtual_path, error=None))
            except Exception as e:
                logger.warning("upload failed for %s: %s", virtual_path, e)
                responses.append(
                    FileUploadResponse(path=virtual_path, error="permission_denied")
                )

        return responses

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        """複数ファイルを Volume からダウンロードする."""
        responses: list[FileDownloadResponse] = []

        for virtual_path in paths:
            real_path = self._real(virtual_path)
            try:
                resp = self.files.download(real_path)
                content = resp.contents.read()
                responses.append(
                    FileDownloadResponse(path=virtual_path, content=content, error=None)
                )
            except (NotFound, ResourceDoesNotExist):
                responses.append(
                    FileDownloadResponse(
                        path=virtual_path, content=None, error="file_not_found"
                    )
                )
            except DatabricksError as e:
                logger.warning("download failed for %s: %s", virtual_path, e)
                responses.append(
                    FileDownloadResponse(
                        path=virtual_path, content=None, error="file_not_found"
                    )
                )
            except Exception as e:
                logger.warning("download failed for %s: %s", virtual_path, e)
                responses.append(
                    FileDownloadResponse(
                        path=virtual_path, content=None, error="permission_denied"
                    )
                )

        return responses
