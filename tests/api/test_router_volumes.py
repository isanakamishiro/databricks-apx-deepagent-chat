"""ボリューム API ルーターテスト."""
from databricks.sdk.errors import NotFound, PermissionDenied
from unittest.mock import MagicMock


def test_list_catalogs_success(client, mock_ws):
    catalog1 = MagicMock()
    catalog1.name = "catalog1"
    catalog2 = MagicMock()
    catalog2.name = "catalog2"
    mock_ws.catalogs.list.return_value = [catalog1, catalog2]
    response = client.get("/api/volumes/catalogs")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["name"] == "catalog1"


def test_list_catalogs_permission_denied(client, mock_ws):
    mock_ws.catalogs.list.side_effect = PermissionDenied("denied")
    response = client.get("/api/volumes/catalogs")
    assert response.status_code == 403


def test_list_schemas_success(client, mock_ws):
    schema1 = MagicMock()
    schema1.name = "schema1"
    mock_ws.schemas.list.return_value = [schema1]
    response = client.get("/api/volumes/schemas", params={"catalog": "my_catalog"})
    assert response.status_code == 200
    data = response.json()
    assert data[0]["name"] == "schema1"


def test_list_schemas_catalog_not_found(client, mock_ws):
    mock_ws.schemas.list.side_effect = NotFound("not found")
    response = client.get("/api/volumes/schemas", params={"catalog": "missing"})
    assert response.status_code == 404


def test_list_schemas_permission_denied(client, mock_ws):
    mock_ws.schemas.list.side_effect = PermissionDenied("denied")
    response = client.get("/api/volumes/schemas", params={"catalog": "cat"})
    assert response.status_code == 403


def test_list_volumes_success(client, mock_ws):
    vol1 = MagicMock()
    vol1.name = "vol1"
    mock_ws.volumes.list.return_value = [vol1]
    response = client.get(
        "/api/volumes/volumes", params={"catalog": "cat", "schema": "sch"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data[0]["name"] == "vol1"


def test_list_volumes_not_found(client, mock_ws):
    mock_ws.volumes.list.side_effect = NotFound("not found")
    response = client.get(
        "/api/volumes/volumes", params={"catalog": "cat", "schema": "missing"}
    )
    assert response.status_code == 404


def test_list_volumes_missing_schema_param(client):
    response = client.get("/api/volumes/volumes", params={"catalog": "cat"})
    assert response.status_code == 422


def test_validate_volume_success(client, mock_ws):
    mock_ws.files.list_directory_contents.return_value = iter([])
    response = client.get(
        "/api/volumes/validate",
        params={"catalog": "cat", "schema": "sch", "volume": "vol"},
    )
    assert response.status_code == 200
    assert response.json() == {"exists": True}


def test_validate_volume_not_found(client, mock_ws):
    mock_ws.files.list_directory_contents.side_effect = NotFound("not found")
    response = client.get(
        "/api/volumes/validate",
        params={"catalog": "cat", "schema": "sch", "volume": "missing"},
    )
    assert response.status_code == 404


def test_validate_volume_permission_denied(client, mock_ws):
    mock_ws.files.list_directory_contents.side_effect = PermissionDenied("denied")
    response = client.get(
        "/api/volumes/validate",
        params={"catalog": "cat", "schema": "sch", "volume": "vol"},
    )
    assert response.status_code == 403
