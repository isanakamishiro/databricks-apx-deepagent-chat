import io
import logging
from pathlib import PurePosixPath
from urllib.parse import quote

logger = logging.getLogger(__name__)

from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound, ResourceDoesNotExist
from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..agent import to_real_path, to_virtual_path
from ..core import Dependencies

router = APIRouter()

ALLOWED_EXTENSIONS = {
    # ドキュメント
    ".txt", ".md", ".html", ".htm", ".css",
    ".py", ".yaml", ".yml", ".json", ".xml", ".csv",
    ".js", ".ts", ".tsx", ".jsx", ".sh", ".sql",
    ".toml", ".ini", ".conf", ".log", ".rst", ".tex",
    ".r", ".rb", ".java", ".c", ".cpp", ".h",
    ".go", ".rs", ".scala", ".kt", ".swift",
    # 画像
    ".png", ".jpg", ".jpeg", ".gif", ".webp",
}

ATTACHMENT_UPLOAD_DIR = "/upload_files/"
MAX_ATTACHMENT_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB


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


class UploadAttachmentResponse(BaseModel):
    ok: bool
    path: str


@router.get("/files/list", operation_id="filesList")
async def files_list(
    volume_path: Dependencies.VolumePath,
    ws: Dependencies.UserClient,
    path: str = Query("/"),
):
    real_path = to_real_path(volume_path, path)

    try:
        entries = list(ws.files.list_directory_contents(real_path))
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
async def files_download(
    volume_path: Dependencies.VolumePath,
    ws: Dependencies.UserClient,
    path: str = Query(...),
):
    real_path = to_real_path(volume_path, path)

    try:
        resp = ws.files.download(real_path)
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

    encoded_filename = quote(filename, encoding="utf-8")
    content_disposition = f"attachment; filename*=utf-8''{encoded_filename}"

    return StreamingResponse(
        iterfile(),
        media_type="application/octet-stream",
        headers={"Content-Disposition": content_disposition},
    )


@router.post("/files/upload", operation_id="filesUpload")
async def files_upload(
    volume_path: Dependencies.VolumePath,
    ws: Dependencies.UserClient,
    path: str = Form(...),
    file: UploadFile = File(...),
):
    upload_dir = path if path.endswith("/") else path + "/"
    virtual_path = upload_dir + (file.filename or "upload")
    real_path = to_real_path(volume_path, virtual_path)

    content = await file.read()
    try:
        ws.files.upload(real_path, io.BytesIO(content), overwrite=True)
    except Exception:
        logger.exception("File upload failed for path: %s", real_path)
        raise HTTPException(status_code=500, detail="Upload failed")

    return {"ok": True, "path": virtual_path}


@router.post("/files/upload-attachment", operation_id="filesUploadAttachment", response_model=UploadAttachmentResponse)
async def files_upload_attachment(
    volume_path: Dependencies.VolumePath,
    ws: Dependencies.UserClient,
    file: UploadFile = File(...),
):
    raw_name = file.filename or "upload"
    # パストラバーサル防止: ディレクトリ成分を除いたベースファイル名のみ使用
    parsed = PurePosixPath(PurePosixPath(raw_name).name)
    original_name = parsed.name
    if not original_name:
        raise HTTPException(status_code=400, detail="Invalid filename.")
    suffix = parsed.suffix.lower()
    stem = parsed.stem

    # ファイルタイプ検証
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {suffix}. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    # /upload_files/ ディレクトリ内の既存ファイル一覧取得
    real_upload_dir = to_real_path(volume_path, ATTACHMENT_UPLOAD_DIR)
    try:
        entries = list(ws.files.list_directory_contents(real_upload_dir))
        existing_names = {
            PurePosixPath(e.path).name for e in entries if e.path is not None
        }
    except (NotFound, ResourceDoesNotExist):
        existing_names = set()

    # ユニークなファイル名を決定
    unique_name = original_name
    counter = 1
    while unique_name in existing_names:
        unique_name = f"{stem}_{counter}{suffix}"
        counter += 1

    virtual_path = str(PurePosixPath(ATTACHMENT_UPLOAD_DIR) / unique_name)
    real_path = to_real_path(volume_path, virtual_path)

    content = await file.read()
    if len(content) > MAX_ATTACHMENT_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {MAX_ATTACHMENT_SIZE_BYTES // (1024 * 1024)} MB.",
        )
    try:
        ws.files.upload(real_path, io.BytesIO(content), overwrite=False)
    except Exception:
        logger.exception("Attachment upload failed for path: %s", real_path)
        raise HTTPException(status_code=500, detail="Upload failed")

    return UploadAttachmentResponse(ok=True, path=virtual_path)


@router.post("/files/mkdir", operation_id="filesMkdir")
async def files_mkdir(
    body: MkdirRequest,
    volume_path: Dependencies.VolumePath,
    ws: Dependencies.UserClient,
):
    dir_path = body.path if body.path.endswith("/") else body.path + "/"
    real_path = to_real_path(volume_path, dir_path)
    try:
        ws.files.create_directory(real_path)
    except Exception:
        logger.exception("Directory creation failed for path: %s", real_path)
        raise HTTPException(status_code=500, detail="Failed to create directory")
    return {"ok": True, "path": dir_path}


@router.delete("/files/delete", operation_id="filesDelete")
async def files_delete(
    volume_path: Dependencies.VolumePath,
    ws: Dependencies.UserClient,
    path: str = Query(...),
    is_dir: bool = Query(False),
):
    real_path = to_real_path(volume_path, path)
    try:
        if is_dir:
            _delete_directory_recursive(ws, real_path)
        else:
            ws.files.delete(real_path)
    except (NotFound, ResourceDoesNotExist):
        raise HTTPException(status_code=404, detail="File or directory not found")
    except Exception:
        logger.exception("Delete failed for path: %s", real_path)
        raise HTTPException(status_code=500, detail="Delete failed")
    return {"ok": True}
