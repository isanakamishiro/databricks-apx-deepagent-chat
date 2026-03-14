def to_real_path(volume_path: str, virtual_path: str) -> str:
    """仮想パスを Unity Catalog Volumes 上の実パスに変換する.

    Args:
        volume_path: Volume のルートパス (例: "/Volumes/catalog/schema/volume").
        virtual_path: 仮想絶対パス (例: "/workspace/plan.md").

    Returns:
        Volumes 上の実パス (例: "/Volumes/catalog/schema/volume/workspace/plan.md").
    """
    vp = virtual_path if virtual_path.startswith("/") else "/" + virtual_path
    result = volume_path.rstrip("/") + vp
    # "/Volumes/.../vol/" のように末尾スラッシュが残る場合は除去 (ルート "/" の場合)
    if result.endswith("/") and len(result) > 1:
        result = result.rstrip("/")
    return result


def to_virtual_path(volume_path: str, real_path: str) -> str:
    """Unity Catalog Volumes 上の実パスを仮想パスに変換する.

    Args:
        volume_path: Volume のルートパス (例: "/Volumes/catalog/schema/volume").
        real_path: Volumes 上の実パス (例: "/Volumes/catalog/schema/volume/workspace/plan.md").
            read_files の _metadata.file_path は "dbfs:" プレフィクス付きの場合がある.

    Returns:
        仮想絶対パス (例: "/workspace/plan.md").
    """
    prefix = volume_path.rstrip("/")
    # read_files の _metadata.file_path は "dbfs:" プレフィクスが付く場合がある
    path = real_path.removeprefix("dbfs:")
    if path.startswith(prefix):
        rest = path[len(prefix) :]
        return rest if rest.startswith("/") else "/" + rest
    return real_path
