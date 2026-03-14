"""UCVolumesBackend ユニットテスト."""
import pytest
from databricks.sdk.errors import NotFound
from unittest.mock import MagicMock

from apx_deepagent_chat.backend.agent.uc_backend import UCVolumesBackend


@pytest.fixture
def mock_ws():
    ws = MagicMock()
    return ws


@pytest.fixture
def backend(mock_ws):
    return UCVolumesBackend(
        volume_path="/Volumes/cat/schema/vol",
        workspace_client=mock_ws,
    )


def _make_download_resp(content: str):
    mock_resp = MagicMock()
    mock_resp.contents.read.return_value = content.encode("utf-8")
    return mock_resp


# ─── パス変換 ─────────────────────────────────────────────────────────────────


def test_to_real_path(backend):
    assert backend._real("/workspace/plan.md") == "/Volumes/cat/schema/vol/workspace/plan.md"


def test_to_virtual_path(backend):
    assert backend._virtual("/Volumes/cat/schema/vol/workspace/plan.md") == "/workspace/plan.md"


# ─── read ─────────────────────────────────────────────────────────────────────


def test_read_file_success(backend, mock_ws):
    mock_ws.files.download.return_value = _make_download_resp("line1\nline2\nline3")
    result = backend.read("/file.txt")
    assert "line1" in result
    assert "line2" in result
    assert "line3" in result


def test_read_file_not_found(backend, mock_ws):
    mock_ws.files.download.side_effect = NotFound("not found")
    result = backend.read("/missing.txt")
    assert "Error" in result
    assert "missing.txt" in result


def test_read_with_offset_and_limit(backend, mock_ws):
    lines = "\n".join(f"line{i}" for i in range(1, 11))
    mock_ws.files.download.return_value = _make_download_resp(lines)
    result = backend.read("/file.txt", offset=2, limit=3)
    assert "line3" in result
    assert "line4" in result
    assert "line5" in result
    assert "line1" not in result
    assert "line6" not in result


def test_read_offset_exceeds_length(backend, mock_ws):
    mock_ws.files.download.return_value = _make_download_resp("only one line")
    result = backend.read("/file.txt", offset=100)
    assert "Error" in result


# ─── write ────────────────────────────────────────────────────────────────────


def test_write_new_file(backend, mock_ws):
    mock_ws.files.get_metadata.side_effect = NotFound("not found")
    result = backend.write("/new_file.txt", "hello world")
    assert result.path == "/new_file.txt"
    assert result.error is None
    mock_ws.files.upload.assert_called_once()


def test_write_existing_file_fails(backend, mock_ws):
    mock_ws.files.get_metadata.return_value = MagicMock()
    result = backend.write("/existing.txt", "content")
    assert result.error is not None
    assert "already exists" in result.error


# ─── edit ─────────────────────────────────────────────────────────────────────


def test_edit_string_replacement(backend, mock_ws):
    mock_ws.files.download.return_value = _make_download_resp("hello world")
    result = backend.edit("/file.txt", "hello", "goodbye")
    assert result.error is None
    assert result.path == "/file.txt"
    mock_ws.files.upload.assert_called_once()
    uploaded = mock_ws.files.upload.call_args[0][1].read().decode("utf-8")
    assert uploaded == "goodbye world"


def test_edit_replace_all(backend, mock_ws):
    mock_ws.files.download.return_value = _make_download_resp("a b a b a")
    result = backend.edit("/file.txt", "a", "x", replace_all=True)
    assert result.error is None
    uploaded = mock_ws.files.upload.call_args[0][1].read().decode("utf-8")
    assert uploaded == "x b x b x"


def test_edit_file_not_found(backend, mock_ws):
    mock_ws.files.download.side_effect = NotFound("not found")
    result = backend.edit("/missing.txt", "old", "new")
    assert result.error is not None
    assert "not found" in result.error.lower()


# ─── ls_info ──────────────────────────────────────────────────────────────────


def test_ls_info_success(backend, mock_ws):
    entry_file = MagicMock()
    entry_file.path = "/Volumes/cat/schema/vol/file.txt"
    entry_file.is_directory = False
    entry_file.file_size = 100
    entry_file.last_modified = "2024-01-01"

    entry_dir = MagicMock()
    entry_dir.path = "/Volumes/cat/schema/vol/subdir"
    entry_dir.is_directory = True
    entry_dir.file_size = None
    entry_dir.last_modified = "2024-01-01"

    mock_ws.files.list_directory_contents.return_value = [entry_file, entry_dir]
    result = backend.ls_info("/")
    paths = [f["path"] for f in result]
    assert "/file.txt" in paths
    assert "/subdir/" in paths


def test_ls_info_hides_dotfiles(backend, mock_ws):
    entry = MagicMock()
    entry.path = "/Volumes/cat/schema/vol/.hidden"
    entry.is_directory = False
    entry.file_size = 10
    entry.last_modified = "2024-01-01"
    mock_ws.files.list_directory_contents.return_value = [entry]
    result = backend.ls_info("/")
    assert len(result) == 0


def test_ls_info_directory_not_found(backend, mock_ws):
    mock_ws.files.list_directory_contents.side_effect = NotFound("not found")
    result = backend.ls_info("/missing")
    assert result == []
