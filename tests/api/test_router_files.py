"""ファイル API ルーターテスト."""
from databricks.sdk.errors import NotFound
from unittest.mock import MagicMock


def test_list_files_success(client, mock_ws, vol_headers):
    entry = MagicMock()
    entry.path = "/Volumes/cat/schema/vol/file.txt"
    entry.is_directory = False
    entry.file_size = 100
    entry.last_modified = "2024-01-01"
    mock_ws.files.list_directory_contents.return_value = [entry]
    response = client.get("/api/files/list", params={"path": "/"}, headers=vol_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "file.txt"


def test_list_files_directory_listing(client, mock_ws, vol_headers):
    file_entry = MagicMock()
    file_entry.path = "/Volumes/cat/schema/vol/doc.txt"
    file_entry.is_directory = False
    file_entry.file_size = 50
    file_entry.last_modified = "2024-01-02"

    dir_entry = MagicMock()
    dir_entry.path = "/Volumes/cat/schema/vol/reports"
    dir_entry.is_directory = True
    dir_entry.file_size = None
    dir_entry.last_modified = "2024-01-01"

    mock_ws.files.list_directory_contents.return_value = [file_entry, dir_entry]
    response = client.get("/api/files/list", params={"path": "/"}, headers=vol_headers)
    assert response.status_code == 200
    data = response.json()
    # ディレクトリが先にソートされる
    assert data[0]["is_dir"] is True
    assert data[0]["name"] == "reports"


def test_list_files_hidden_excluded(client, mock_ws, vol_headers):
    entry = MagicMock()
    entry.path = "/Volumes/cat/schema/vol/.hidden"
    entry.is_directory = False
    entry.file_size = 10
    entry.last_modified = "2024-01-01"
    mock_ws.files.list_directory_contents.return_value = [entry]
    response = client.get("/api/files/list", params={"path": "/"}, headers=vol_headers)
    assert response.status_code == 200
    assert len(response.json()) == 0


def test_list_files_missing_volume_path(client):
    response = client.get("/api/files/list", params={"path": "/"})
    assert response.status_code == 400


def test_list_files_directory_not_found(client, mock_ws, vol_headers):
    mock_ws.files.list_directory_contents.side_effect = NotFound("not found")
    response = client.get("/api/files/list", params={"path": "/"}, headers=vol_headers)
    assert response.status_code == 404


def test_download_success(client, mock_ws, vol_headers):
    mock_resp = MagicMock()
    mock_resp.contents = MagicMock()
    mock_resp.contents.read.side_effect = [b"file content", b""]
    mock_ws.files.download.return_value = mock_resp
    response = client.get(
        "/api/files/download", params={"path": "/file.txt"}, headers=vol_headers
    )
    assert response.status_code == 200


def test_download_not_found(client, mock_ws, vol_headers):
    mock_ws.files.download.side_effect = NotFound("not found")
    response = client.get(
        "/api/files/download", params={"path": "/missing.txt"}, headers=vol_headers
    )
    assert response.status_code == 404


def test_upload_success(client, vol_headers):
    response = client.post(
        "/api/files/upload",
        data={"path": "/uploads/"},
        files={"file": ("test.txt", b"file content", "text/plain")},
        headers=vol_headers,
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_mkdir_success(client, vol_headers):
    response = client.post(
        "/api/files/mkdir",
        json={"path": "/new_dir"},
        headers=vol_headers,
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_delete_file_success(client, vol_headers):
    response = client.delete(
        "/api/files/delete", params={"path": "/file.txt"}, headers=vol_headers
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_delete_not_found(client, mock_ws, vol_headers):
    mock_ws.files.delete.side_effect = NotFound("not found")
    response = client.delete(
        "/api/files/delete", params={"path": "/missing.txt"}, headers=vol_headers
    )
    assert response.status_code == 404
