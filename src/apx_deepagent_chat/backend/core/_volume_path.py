from __future__ import annotations

from typing import Annotated, TypeAlias

from fastapi import Depends, Header, HTTPException


def _get_volume_path(
    x_uc_volume_path: Annotated[str | None, Header(alias="x-uc-volume-path")] = None,
) -> str:
    if not x_uc_volume_path:
        raise HTTPException(status_code=400, detail="x-uc-volume-path header required")
    return x_uc_volume_path


VolumePathDependency: TypeAlias = Annotated[str, Depends(_get_volume_path)]
