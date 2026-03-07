import io
from pathlib import PurePosixPath

from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound, ResourceDoesNotExist
from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..agent_utils import to_real_path, to_virtual_path

router = APIRouter()


def _extract_volume_path(request: Request) -> str:
    vp = request.headers.get("x-uc-volume-path", "")
    if not vp:
        raise HTTPException(status_code=400, detail="x-uc-volume-path header required")
    return vp


def _delete_directory_recursive(w: WorkspaceClient, dir_path: str):
    """ディレクトリ内を再帰削除し、ディレクトリ自体も削除する."""
    try:
        entries = list(w.files.list_directory_contents(dir_path))
    except (NotFound, ResourceDoesNotExist):
        return
    for entry in entries:
        if entry.path is None:
            continue
        if entry.is_directory:
            _delete_directory_recursive(w, entry.path)
        else:
            w.files.delete(entry.path)
    w.files.delete_directory(dir_path)


class MkdirRequest(BaseModel):
    path: str  # 作成先の仮想パス (例: "/reports/2024/")


@router.get("/files/list", operation_id="filesList")
async def files_list(request: Request, path: str = Query("/")):
    volume_path = _extract_volume_path(request)
    real_path = to_real_path(volume_path, path)
    w = WorkspaceClient()

    try:
        entries = list(w.files.list_directory_contents(real_path))
    except (NotFound, ResourceDoesNotExist):
        raise HTTPException(status_code=404, detail="Directory not found")

    result = []
    for entry in entries:
        if entry.path is None:
            continue
        basename = PurePosixPath(entry.path).name
        if basename.startswith("."):
            continue
        is_dir = entry.is_directory or False
        virtual = to_virtual_path(volume_path, entry.path)
        item: dict = {
            "name": basename,
            "path": virtual + "/" if is_dir else virtual,
            "is_dir": is_dir,
        }
        if not is_dir and entry.file_size is not None:
            item["size"] = int(entry.file_size)
        if entry.last_modified is not None:
            item["modified_at"] = str(entry.last_modified)
        result.append(item)

    result.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
    return result


@router.get("/files/download", operation_id="filesDownload")
async def files_download(request: Request, path: str = Query(...)):
    volume_path = _extract_volume_path(request)
    real_path = to_real_path(volume_path, path)
    w = WorkspaceClient()

    try:
        resp = w.files.download(real_path)
    except (NotFound, ResourceDoesNotExist):
        raise HTTPException(status_code=404, detail="File not found")

    if resp.contents is None:
        raise HTTPException(status_code=404, detail="File not found")

    filename = PurePosixPath(path).name
    contents = resp.contents

    def iterfile():
        while True:
            chunk = contents.read(8192)
            if not chunk:
                break
            yield chunk

    return StreamingResponse(
        iterfile(),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/files/upload", operation_id="filesUpload")
async def files_upload(
    request: Request,
    path: str = Form(...),
    file: UploadFile = File(...),
):
    volume_path = _extract_volume_path(request)
    upload_dir = path if path.endswith("/") else path + "/"
    virtual_path = upload_dir + (file.filename or "upload")
    real_path = to_real_path(volume_path, virtual_path)
    w = WorkspaceClient()

    content = await file.read()
    try:
        w.files.upload(real_path, io.BytesIO(content), overwrite=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {e}")

    return {"ok": True, "path": virtual_path}


@router.post("/files/mkdir", operation_id="filesMkdir")
async def files_mkdir(body: MkdirRequest, request: Request):
    volume_path = _extract_volume_path(request)
    dir_path = body.path if body.path.endswith("/") else body.path + "/"
    real_path = to_real_path(volume_path, dir_path)
    w = WorkspaceClient()
    try:
        w.files.create_directory(real_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create directory: {e}")
    return {"ok": True, "path": dir_path}


@router.delete("/files/delete", operation_id="filesDelete")
async def files_delete(
    request: Request, path: str = Query(...), is_dir: bool = Query(False)
):
    volume_path = _extract_volume_path(request)
    real_path = to_real_path(volume_path, path)
    w = WorkspaceClient()
    try:
        if is_dir:
            _delete_directory_recursive(w, real_path)
        else:
            w.files.delete(real_path)
    except (NotFound, ResourceDoesNotExist):
        raise HTTPException(status_code=404, detail="File or directory not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Delete failed: {e}")
    return {"ok": True}
