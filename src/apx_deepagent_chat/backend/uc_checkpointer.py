"""LangGraph BaseCheckpointSaver backed by Databricks Unity Catalog Volumes.

Stores checkpoint state, intermediate writes, and channel blobs as JSON files
on a UC Volume using the Databricks SDK Files API.

Directory layout under ``{volume_path}/{checkpoint_dir}/``:

    checkpoints/{thread_id}/{checkpoint_ns}/{checkpoint_id}.json
    writes/{thread_id}/{checkpoint_ns}/{checkpoint_id}/{task_id}_{write_idx}.json
    blobs/{thread_id}/{checkpoint_ns}/{channel}_{version}.json
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import random
from collections.abc import AsyncIterator, Iterator, Sequence
from contextlib import AbstractAsyncContextManager, AbstractContextManager
from pathlib import PurePosixPath
from typing import Any, List

from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import DatabricksError, NotFound, ResourceDoesNotExist
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    WRITES_IDX_MAP,
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    SerializerProtocol,
    get_checkpoint_id,
    get_checkpoint_metadata,
)

logger = logging.getLogger(__name__)

_ROOT_NS = "__root__"


def _encode_ns(ns: str) -> str:
    """Encode checkpoint namespace for use as a directory name."""
    return _ROOT_NS if ns == "" else ns


def _decode_ns(encoded: str) -> str:
    """Decode directory name back to checkpoint namespace."""
    return "" if encoded == _ROOT_NS else encoded


def _safe_version(version: str | int | float) -> str:
    """Encode a channel version for safe use in filenames."""
    return str(version).replace("/", "_").replace(".", "_dot_")


class UCVolumesCheckpointer(
    BaseCheckpointSaver[str],
    AbstractContextManager,
    AbstractAsyncContextManager,
):
    """Checkpoint saver that persists state to UC Volumes via the Files API.

    Args:
        volume_path: UC Volume root path (e.g. ``/Volumes/catalog/schema/volume``).
        workspace_client: ``WorkspaceClient`` for Files API access.
            ``None`` to use default authentication.
        checkpoint_dir: Sub-directory name under *volume_path*.  Default ``".checkpoints"``.
        serde: Optional custom serializer.
    """

    def __init__(
        self,
        volume_path: str,
        workspace_client: WorkspaceClient | None = None,
        checkpoint_dir: str = ".checkpoints",
        *,
        serde: SerializerProtocol | None = None,
    ) -> None:
        super().__init__(serde=serde)
        self._volume_path = volume_path.rstrip("/")
        self._w = workspace_client or WorkspaceClient()
        self._base = f"{self._volume_path}/{checkpoint_dir}"

    # ------------------------------------------------------------------
    # Context manager support
    # ------------------------------------------------------------------

    def __enter__(self) -> UCVolumesCheckpointer:
        return self

    def __exit__(self, *exc_info: Any) -> None:
        pass

    async def __aenter__(self) -> UCVolumesCheckpointer:
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        pass

    # ------------------------------------------------------------------
    # Path helpers
    # ------------------------------------------------------------------

    def _ckpt_dir(self, thread_id: str, ns: str) -> str:
        return f"{self._base}/checkpoints/{thread_id}/{_encode_ns(ns)}"

    def _ckpt_path(self, thread_id: str, ns: str, ckpt_id: str) -> str:
        return f"{self._ckpt_dir(thread_id, ns)}/{ckpt_id}.json"

    def _writes_dir(self, thread_id: str, ns: str, ckpt_id: str) -> str:
        return f"{self._base}/writes/{thread_id}/{_encode_ns(ns)}/{ckpt_id}"

    def _write_path(
        self, thread_id: str, ns: str, ckpt_id: str, task_id: str, idx: int
    ) -> str:
        return f"{self._writes_dir(thread_id, ns, ckpt_id)}/{task_id}_{idx}.json"

    def _blob_path(
        self, thread_id: str, ns: str, channel: str, version: str | int | float
    ) -> str:
        safe_ch = channel.replace("/", "_")
        return (
            f"{self._base}/blobs/{thread_id}/{_encode_ns(ns)}/"
            f"{safe_ch}_{_safe_version(version)}.json"
        )

    # ------------------------------------------------------------------
    # Low-level file helpers (synchronous, mirrors UCVolumesBackend)
    # ------------------------------------------------------------------

    @property
    def files(self):
        """Databricks Files API client."""
        return self._w.files

    def _ensure_dir(self, path: str) -> None:
        parent = str(PurePosixPath(path).parent)
        try:
            self.files.create_directory(parent)
        except Exception:
            pass

    def _upload_json(self, path: str, data: dict) -> None:
        self._ensure_dir(path)
        content = json.dumps(data).encode("utf-8")
        self.files.upload(path, io.BytesIO(content), overwrite=True)

    def _download_json(self, path: str) -> dict | None:
        try:
            resp = self.files.download(path)
            return json.loads(resp.contents.read().decode("utf-8"))
        except (NotFound, ResourceDoesNotExist):
            return None
        except DatabricksError as e:
            logger.warning("_download_json failed for %s: %s", path, e)
            return None

    def _file_exists(self, path: str) -> bool:
        try:
            self.files.get_metadata(path)
            return True
        except (NotFound, ResourceDoesNotExist):
            return False
        except DatabricksError as e:
            logger.warning("_file_exists failed for %s: %s", path, e)
            return False

    def _list_dir(self, path: str) -> "List[Any]":
        try:
            return list(self.files.list_directory_contents(path))
        except (NotFound, ResourceDoesNotExist):
            return []
        except DatabricksError as e:
            logger.warning("_list_dir failed for %s: %s", path, e)
            return []

    def _delete_recursive(self, path: str) -> None:
        entries = self._list_dir(path)
        for entry in entries:
            if entry.path is None:
                continue
            if entry.is_directory:
                self._delete_recursive(entry.path)
            else:
                try:
                    self.files.delete(entry.path)
                except Exception:
                    pass
        try:
            self.files.delete_directory(path)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Serialization helpers (serde.dumps_typed → JSON-safe list)
    # ------------------------------------------------------------------

    def _serialize_typed(self, obj: Any) -> list:  # type: ignore[valid-type]
        """Return ``[type_str, base64_data]`` via ``serde.dumps_typed``."""
        type_str, raw_bytes = self.serde.dumps_typed(obj)
        return [type_str, base64.b64encode(raw_bytes).decode("ascii")]

    def _deserialize_typed(self, data: list) -> Any:  # type: ignore[valid-type]
        """Inverse of :meth:`_serialize_typed`."""
        type_str, b64_data = data
        raw_bytes = base64.b64decode(b64_data)
        return self.serde.loads_typed((type_str, raw_bytes))

    # ------------------------------------------------------------------
    # Blob / write loading
    # ------------------------------------------------------------------

    def _load_blobs(
        self, thread_id: str, ns: str, versions: ChannelVersions
    ) -> dict[str, Any]:
        channel_values: dict[str, Any] = {}
        for channel, version in versions.items():
            blob_data = self._download_json(
                self._blob_path(thread_id, ns, channel, version)
            )
            if blob_data and blob_data.get("type") != "empty":
                channel_values[channel] = self._deserialize_typed(
                    [blob_data["type"], blob_data["data"]]
                )
        return channel_values

    def _load_writes(
        self, thread_id: str, ns: str, ckpt_id: str
    ) -> list[tuple[str, str, Any]]:  # type: ignore[valid-type]
        writes_dir = self._writes_dir(thread_id, ns, ckpt_id)
        entries = self._list_dir(writes_dir)
        writes: list[tuple[str, str, Any]] = []
        for entry in entries:
            if entry.path is None or entry.is_directory:
                continue
            data = self._download_json(entry.path)
            if data:
                writes.append(
                    (
                        data["task_id"],
                        data["channel"],
                        self._deserialize_typed(data["value"]),
                    )
                )
        return writes

    # ------------------------------------------------------------------
    # BaseCheckpointSaver – synchronous implementation
    # ------------------------------------------------------------------

    def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        thread_id: str = config["configurable"]["thread_id"]
        ns: str = config["configurable"].get("checkpoint_ns", "")

        if checkpoint_id := get_checkpoint_id(config):
            data = self._download_json(
                self._ckpt_path(thread_id, ns, checkpoint_id)
            )
            if not data:
                return None
            checkpoint = self._deserialize_typed(data["checkpoint"])
            metadata = self._deserialize_typed(data["metadata"])
            parent_id = data.get("parent_checkpoint_id")
            writes = self._load_writes(thread_id, ns, checkpoint_id)
            return CheckpointTuple(
                config=config,
                checkpoint={  # type: ignore[typeddict-item]
                    **checkpoint,
                    "channel_values": self._load_blobs(
                        thread_id, ns, checkpoint["channel_versions"]
                    ),
                },
                metadata=metadata,
                pending_writes=writes,
                parent_config=(
                    {
                        "configurable": {
                            "thread_id": thread_id,
                            "checkpoint_ns": ns,
                            "checkpoint_id": parent_id,
                        }
                    }
                    if parent_id
                    else None
                ),
            )
        else:
            # Get latest checkpoint (max checkpoint_id)
            ckpt_dir = self._ckpt_dir(thread_id, ns)
            entries = self._list_dir(ckpt_dir)
            ckpt_ids = [
                PurePosixPath(e.path).stem
                for e in entries
                if e.path and not e.is_directory
            ]
            if not ckpt_ids:
                return None
            checkpoint_id = max(ckpt_ids)
            data = self._download_json(
                self._ckpt_path(thread_id, ns, checkpoint_id)
            )
            if not data:
                return None
            checkpoint = self._deserialize_typed(data["checkpoint"])
            metadata = self._deserialize_typed(data["metadata"])
            parent_id = data.get("parent_checkpoint_id")
            writes = self._load_writes(thread_id, ns, checkpoint_id)
            return CheckpointTuple(
                config={
                    "configurable": {
                        "thread_id": thread_id,
                        "checkpoint_ns": ns,
                        "checkpoint_id": checkpoint_id,
                    }
                },
                checkpoint={  # type: ignore[typeddict-item]
                    **checkpoint,
                    "channel_values": self._load_blobs(
                        thread_id, ns, checkpoint["channel_versions"]
                    ),
                },
                metadata=metadata,
                pending_writes=writes,
                parent_config=(
                    {
                        "configurable": {
                            "thread_id": thread_id,
                            "checkpoint_ns": ns,
                            "checkpoint_id": parent_id,
                        }
                    }
                    if parent_id
                    else None
                ),
            )

    def list(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> Iterator[CheckpointTuple]:
        if config:
            thread_ids = [config["configurable"]["thread_id"]]
        else:
            entries = self._list_dir(f"{self._base}/checkpoints")
            thread_ids = [
                PurePosixPath(e.path).name
                for e in entries
                if e.path and e.is_directory
            ]

        config_ns = (
            config["configurable"].get("checkpoint_ns") if config else None
        )
        config_ckpt_id = get_checkpoint_id(config) if config else None
        before_ckpt_id = get_checkpoint_id(before) if before else None

        count = 0
        for thread_id in thread_ids:
            thread_dir = f"{self._base}/checkpoints/{thread_id}"
            ns_entries = self._list_dir(thread_dir)
            for ns_entry in ns_entries:
                if not ns_entry.path or not ns_entry.is_directory:
                    continue
                ns = _decode_ns(PurePosixPath(ns_entry.path).name)
                if config_ns is not None and ns != config_ns:
                    continue

                ckpt_entries = self._list_dir(ns_entry.path)
                ckpt_ids = sorted(
                    [
                        PurePosixPath(e.path).stem
                        for e in ckpt_entries
                        if e.path and not e.is_directory
                    ],
                    reverse=True,
                )
                for ckpt_id in ckpt_ids:
                    if config_ckpt_id and ckpt_id != config_ckpt_id:
                        continue
                    if before_ckpt_id and ckpt_id >= before_ckpt_id:
                        continue

                    data = self._download_json(
                        self._ckpt_path(thread_id, ns, ckpt_id)
                    )
                    if not data:
                        continue
                    metadata = self._deserialize_typed(data["metadata"])
                    if filter and not all(
                        metadata.get(k) == v for k, v in filter.items()
                    ):
                        continue

                    if limit is not None and count >= limit:
                        return

                    checkpoint = self._deserialize_typed(data["checkpoint"])
                    parent_id = data.get("parent_checkpoint_id")
                    writes = self._load_writes(thread_id, ns, ckpt_id)

                    yield CheckpointTuple(
                        config={
                            "configurable": {
                                "thread_id": thread_id,
                                "checkpoint_ns": ns,
                                "checkpoint_id": ckpt_id,
                            }
                        },
                        checkpoint={  # type: ignore[typeddict-item]
                            **checkpoint,
                            "channel_values": self._load_blobs(
                                thread_id, ns, checkpoint["channel_versions"]
                            ),
                        },
                        metadata=metadata,
                        parent_config=(
                            {
                                "configurable": {
                                    "thread_id": thread_id,
                                    "checkpoint_ns": ns,
                                    "checkpoint_id": parent_id,
                                }
                            }
                            if parent_id
                            else None
                        ),
                        pending_writes=writes,
                    )
                    count += 1

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        c = checkpoint.copy()
        thread_id = config["configurable"]["thread_id"]
        ns = config["configurable"].get("checkpoint_ns", "")
        values: dict[str, Any] = c.pop("channel_values")  # type: ignore[misc]

        # Store blobs first (commit point is the checkpoint file)
        for channel, version in new_versions.items():
            if channel in values:
                type_str, raw = self.serde.dumps_typed(values[channel])
            else:
                type_str, raw = "empty", b""
            blob_data = {
                "type": type_str,
                "data": base64.b64encode(raw).decode("ascii"),
            }
            self._upload_json(
                self._blob_path(thread_id, ns, channel, version), blob_data
            )

        # Store checkpoint
        ckpt_data = {
            "checkpoint": self._serialize_typed(c),
            "metadata": self._serialize_typed(
                get_checkpoint_metadata(config, metadata)
            ),
            "parent_checkpoint_id": config["configurable"].get("checkpoint_id"),
        }
        self._upload_json(
            self._ckpt_path(thread_id, ns, checkpoint["id"]), ckpt_data
        )

        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": ns,
                "checkpoint_id": checkpoint["id"],
            }
        }

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        thread_id = config["configurable"]["thread_id"]
        ns = config["configurable"].get("checkpoint_ns", "")
        ckpt_id = config["configurable"]["checkpoint_id"]

        for idx, (channel, value) in enumerate(writes):
            write_idx = WRITES_IDX_MAP.get(channel, idx)
            write_file = self._write_path(
                thread_id, ns, ckpt_id, task_id, write_idx
            )
            if write_idx >= 0 and self._file_exists(write_file):
                continue

            write_data = {
                "task_id": task_id,
                "channel": channel,
                "value": self._serialize_typed(value),
                "task_path": task_path,
            }
            self._upload_json(write_file, write_data)

    def delete_thread(self, thread_id: str) -> None:
        self._delete_recursive(f"{self._base}/checkpoints/{thread_id}")
        self._delete_recursive(f"{self._base}/writes/{thread_id}")
        self._delete_recursive(f"{self._base}/blobs/{thread_id}")

    # ------------------------------------------------------------------
    # BaseCheckpointSaver – async implementation (via asyncio.to_thread)
    # ------------------------------------------------------------------

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        return await asyncio.to_thread(self.get_tuple, config)

    async def alist(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[CheckpointTuple]:
        results = await asyncio.to_thread(
            lambda: list(
                self.list(config, filter=filter, before=before, limit=limit)
            )
        )
        for item in results:
            yield item

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        return await asyncio.to_thread(
            self.put, config, checkpoint, metadata, new_versions
        )

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        await asyncio.to_thread(self.put_writes, config, writes, task_id, task_path)

    async def adelete_thread(self, thread_id: str) -> None:
        await asyncio.to_thread(self.delete_thread, thread_id)

    # ------------------------------------------------------------------
    # Version generation (matches InMemorySaver)
    # ------------------------------------------------------------------

    def get_next_version(self, current: str | None, channel: None) -> str:
        if current is None:
            current_v = 0
        elif isinstance(current, int):
            current_v = current
        else:
            current_v = int(current.split(".")[0])
        next_v = current_v + 1
        next_h = random.random()
        return f"{next_v:032}.{next_h:016}"
