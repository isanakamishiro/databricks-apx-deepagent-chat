"""
Databricks Unity Catalog (UC) Volumesをバックエンドとして利用するLangGraph BaseCheckpointSaver。

Databricks SDKのFiles APIを使用し、チェックポイントの状態、中間書き込み（intermediate writes）、
およびチャネルBlobをJSONファイルとしてUC Volume上に保存します。

`{volume_path}/{checkpoint_dir}/` 配下のディレクトリ構成：

- checkpoints/{thread_id}/{checkpoint_ns}/{checkpoint_id}.json
- writes/{thread_id}/{checkpoint_ns}/{checkpoint_id}/{task_id}_{write_idx}.json
- blobs/{thread_id}/{checkpoint_ns}/{channel}_{version}.json

UCBundleCheckpointerは、スレッドごとに単一の bundle.json を使用します：

.checkpoints/{thread_id}/bundle.json

"""

from __future__ import annotations

import asyncio
import base64
import gzip
import io
import json
import logging
import random
import time
from collections.abc import AsyncIterator, Iterator, Sequence
from contextlib import AbstractAsyncContextManager, AbstractContextManager
from pathlib import PurePosixPath
from typing import Any, List

import mlflow
from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import DatabricksError, NotFound, ResourceDoesNotExist
from langchain_core.messages import ToolMessage
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
from langgraph.checkpoint.memory import InMemorySaver

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
        self._created_dirs: set[str] = set()

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
        if parent in self._created_dirs:
            return
        try:
            self.files.create_directory(parent)
            self._created_dirs.add(parent)
        except Exception:
            # ディレクトリが既に存在する場合も成功とみなしキャッシュに追加
            self._created_dirs.add(parent)

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
            data = self._download_json(self._ckpt_path(thread_id, ns, checkpoint_id))
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
            data = self._download_json(self._ckpt_path(thread_id, ns, checkpoint_id))
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
                PurePosixPath(e.path).name for e in entries if e.path and e.is_directory
            ]

        config_ns = config["configurable"].get("checkpoint_ns") if config else None
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

                    data = self._download_json(self._ckpt_path(thread_id, ns, ckpt_id))
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
        self._upload_json(self._ckpt_path(thread_id, ns, checkpoint["id"]), ckpt_data)

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
            write_file = self._write_path(thread_id, ns, ckpt_id, task_id, write_idx)
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
            lambda: list(self.list(config, filter=filter, before=before, limit=limit))
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
        t0 = time.monotonic()
        c = checkpoint.copy()
        thread_id: str = config["configurable"]["thread_id"]
        ns: str = config["configurable"].get("checkpoint_ns", "")
        values: dict[str, Any] = c.pop("channel_values")  # type: ignore[misc]

        async def _upload_blob(channel: str, version: Any) -> None:
            if channel in values:
                type_str, raw = self.serde.dumps_typed(values[channel])
            else:
                type_str, raw = "empty", b""
            blob_data = {
                "type": type_str,
                "data": base64.b64encode(raw).decode("ascii"),
            }
            await asyncio.to_thread(
                self._upload_json,
                self._blob_path(thread_id, ns, channel, version),
                blob_data,
            )

        # Upload all blobs in parallel, then commit checkpoint file
        await asyncio.gather(*(_upload_blob(ch, v) for ch, v in new_versions.items()))

        ckpt_data = {
            "checkpoint": self._serialize_typed(c),
            "metadata": self._serialize_typed(
                get_checkpoint_metadata(config, metadata)
            ),
            "parent_checkpoint_id": config["configurable"].get("checkpoint_id"),
        }
        await asyncio.to_thread(
            self._upload_json,
            self._ckpt_path(thread_id, ns, checkpoint["id"]),
            ckpt_data,
        )

        logger.info(
            "[checkpointer] aput took: %.3fs, channels=%d",
            time.monotonic() - t0,
            len(new_versions),
        )
        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": ns,
                "checkpoint_id": checkpoint["id"],
            }
        }

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        t0 = time.monotonic()
        thread_id: str = config["configurable"]["thread_id"]
        ns: str = config["configurable"].get("checkpoint_ns", "")
        ckpt_id: str = config["configurable"]["checkpoint_id"]

        async def _upload_write(idx: int, channel: str, value: Any) -> None:
            write_idx = WRITES_IDX_MAP.get(channel, idx)
            write_file = self._write_path(thread_id, ns, ckpt_id, task_id, write_idx)
            if write_idx >= 0 and await asyncio.to_thread(
                self._file_exists, write_file
            ):
                return
            write_data = {
                "task_id": task_id,
                "channel": channel,
                "value": self._serialize_typed(value),
                "task_path": task_path,
            }
            await asyncio.to_thread(self._upload_json, write_file, write_data)

        await asyncio.gather(
            *(_upload_write(idx, ch, val) for idx, (ch, val) in enumerate(writes))
        )
        logger.info(
            "[checkpointer] aput_writes took: %.3fs, writes=%d",
            time.monotonic() - t0,
            len(writes),
        )

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


class UCBundleCheckpointer(InMemorySaver):
    """UC Volumes backed checkpointer using a single bundle.json.gz per thread.

    Loads all state from UC in ``__aenter__`` (1 API call) and saves back in
    ``__aexit__`` (1 API call).  All get/put operations during a turn run
    entirely in memory using InMemorySaver.

    Bundle path::

        {volume_path}/.checkpoints/{thread_id}/bundle.json.gz

    Falls back to legacy ``bundle.json`` (uncompressed) if ``.gz`` is not found.

    Bundle JSON format (gzip-compressed)::

        {
            "version": 1,
            "storage": [[ns, ckpt_id, ckpt_type, ckpt_b64, meta_type, meta_b64, parent_id|null], ...],
            "writes":  [[ns, ckpt_id, task_id, write_idx, channel, val_type, val_b64, task_path], ...],
            "blobs":   [[ns, channel, version_str, type_str, b64_data], ...]
        }
    """

    def __init__(
        self,
        volume_path: str,
        thread_id: str,
        workspace_client: WorkspaceClient | None = None,
        *,
        serde: SerializerProtocol | None = None,
    ) -> None:
        super().__init__(serde=serde)
        self._thread_id = thread_id
        self._w = workspace_client or WorkspaceClient()
        self._bundle_path = (
            f"{volume_path.rstrip('/')}/.checkpoints/{thread_id}/bundle.json.gz"
        )
        self._save_lock: asyncio.Lock = asyncio.Lock()
        self._bg_save_task: asyncio.Task | None = None

    @property
    def _files(self):
        return self._w.files

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------
    @mlflow.trace(span_type="UNKNOWN")
    async def __aenter__(self) -> "UCBundleCheckpointer":
        t0 = time.monotonic()
        await asyncio.to_thread(self._load_bundle)
        logger.info("[bundle] load took: %.3fs", time.monotonic() - t0)
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        # バックグラウンド保存が進行中なら完了を待つ（最終保存と競合しないよう）
        if self._bg_save_task is not None and not self._bg_save_task.done():
            try:
                await asyncio.wait_for(asyncio.shield(self._bg_save_task), timeout=30.0)
            except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
                logger.warning(
                    "[bundle] background save did not finish before exit", exc_info=True
                )

        t0 = time.monotonic()
        await asyncio.to_thread(self._save_bundle)
        logger.info("[bundle] save took: %.3fs", time.monotonic() - t0)

    # ------------------------------------------------------------------
    # aput override: ツール呼び出し完了時にバックグラウンド保存をトリガー
    # ------------------------------------------------------------------

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        result = await super().aput(config, checkpoint, metadata, new_versions)
        # 最後のメッセージがToolMessageのとき（ツール呼び出し完了直後）にバックグラウンド保存
        messages = (checkpoint.get("channel_values") or {}).get("messages") or []
        if messages and isinstance(messages[-1], ToolMessage):
            self._bg_save_task = asyncio.create_task(
                self._run_background_save(),
                name=f"bg-bundle-save-{self._thread_id}",
            )
            self._bg_save_task.add_done_callback(self._on_bg_save_done)
        return result

    async def _run_background_save(self) -> None:
        """バックグラウンド保存を試みる。保存中なら即スキップ。"""
        if self._save_lock.locked():
            logger.debug("[bundle] background save skipped (already in progress)")
            return
        async with self._save_lock:
            t0 = time.monotonic()
            try:
                # スナップショットはイベントループスレッドで取得（GILによりデータ競合を防ぐ）
                content = self._snapshot_bundle()
                # アップロードはスレッドプールで非同期実行
                await asyncio.to_thread(self._upload_bundle, content)
                logger.info(
                    "[bundle] background save took: %.3fs", time.monotonic() - t0
                )
            except Exception:
                logger.warning(
                    "[bundle] background save failed (non-fatal)", exc_info=True
                )

    def _on_bg_save_done(self, task: asyncio.Task) -> None:
        if self._bg_save_task is task:
            self._bg_save_task = None

    # ------------------------------------------------------------------
    # Bundle I/O
    # ------------------------------------------------------------------

    def load_bundle(self) -> None:
        return self._load_bundle()

    def _load_bundle(self) -> None:
        """Download bundle.json.gz and populate InMemorySaver storage."""
        try:
            resp = self._files.download(self._bundle_path)
            if resp.contents is None:
                return
            raw = gzip.decompress(resp.contents.read())
        except (NotFound, ResourceDoesNotExist):
            return  # 新規会話 — nothing to load
        except DatabricksError as e:
            logger.warning("[bundle] load failed: %s", e)
            return

        bundle = json.loads(raw.decode("utf-8"))

        thread_id = self._thread_id

        # storage: [[ns, ckpt_id, ckpt_type, ckpt_b64, meta_type, meta_b64, parent_id|null], ...]
        for row in bundle.get("storage", []):
            ns, ckpt_id, ckpt_type, ckpt_b64, meta_type, meta_b64, parent_id = row
            ckpt_bytes: tuple[str, bytes] = (ckpt_type, base64.b64decode(ckpt_b64))
            meta_bytes: tuple[str, bytes] = (meta_type, base64.b64decode(meta_b64))
            self.storage[thread_id][ns][ckpt_id] = (ckpt_bytes, meta_bytes, parent_id)

        # writes: [[ns, ckpt_id, task_id, write_idx, channel, val_type, val_b64, task_path], ...]
        for row in bundle.get("writes", []):
            ns, ckpt_id, task_id, write_idx, channel, val_type, val_b64, task_path = row
            outer_key = (thread_id, ns, ckpt_id)
            inner_key = (task_id, int(write_idx))
            val_bytes: tuple[str, bytes] = (val_type, base64.b64decode(val_b64))
            self.writes[outer_key][inner_key] = (task_id, channel, val_bytes, task_path)

        # blobs: [[ns, channel, version_str, type_str, b64_data], ...]
        for row in bundle.get("blobs", []):
            ns, channel, version_str, type_str, b64_data = row
            blob_bytes: tuple[str, bytes] = (type_str, base64.b64decode(b64_data))
            self.blobs[(thread_id, ns, channel, version_str)] = blob_bytes

    def _snapshot_bundle(self) -> bytes:
        """インメモリ状態をgzipバイト列にシリアライズする（イベントループスレッドから呼ぶこと）。

        イベントループスレッドで同期実行することで、GILが辞書イテレーション中に
        他スレッドからの書き込みをブロックし、データ競合を防ぐ。
        """
        thread_id = self._thread_id

        storage_rows = []
        for ns, ns_data in self.storage.get(thread_id, {}).items():
            for ckpt_id, (ckpt_bytes, meta_bytes, parent_id) in ns_data.items():
                storage_rows.append(
                    [
                        ns,
                        ckpt_id,
                        ckpt_bytes[0],
                        base64.b64encode(ckpt_bytes[1]).decode("ascii"),
                        meta_bytes[0],
                        base64.b64encode(meta_bytes[1]).decode("ascii"),
                        parent_id,
                    ]
                )

        writes_rows = []
        for (tid, ns, ckpt_id), inner_writes in self.writes.items():
            if tid != thread_id:
                continue
            for (task_id, write_idx), (
                t_id,
                channel,
                val_bytes,
                t_path,
            ) in inner_writes.items():
                writes_rows.append(
                    [
                        ns,
                        ckpt_id,
                        t_id,
                        write_idx,
                        channel,
                        val_bytes[0],
                        base64.b64encode(val_bytes[1]).decode("ascii"),
                        t_path,
                    ]
                )

        blobs_rows = []
        for (tid, ns, channel, version), blob_bytes in self.blobs.items():
            if tid != thread_id:
                continue
            blobs_rows.append(
                [
                    ns,
                    channel,
                    str(version),
                    blob_bytes[0],
                    base64.b64encode(blob_bytes[1]).decode("ascii"),
                ]
            )

        bundle = {
            "version": 1,
            "storage": storage_rows,
            "writes": writes_rows,
            "blobs": blobs_rows,
        }
        return gzip.compress(json.dumps(bundle).encode("utf-8"), compresslevel=6)

    def _upload_bundle(self, content: bytes) -> None:
        """シリアライズ済みバイト列をUCにアップロードする（スレッドプールから呼んで可）。"""
        bundle_dir = str(PurePosixPath(self._bundle_path).parent)
        try:
            self._files.create_directory(bundle_dir)
        except Exception:
            pass
        self._files.upload(self._bundle_path, io.BytesIO(content), overwrite=True)

    @mlflow.trace(span_type="UNKNOWN")
    def _save_bundle(self) -> None:
        """Serialize InMemorySaver storage and upload as bundle.json."""
        self._upload_bundle(self._snapshot_bundle())

    # ------------------------------------------------------------------
    # Delete thread
    # ------------------------------------------------------------------

    async def adelete_thread(self, thread_id: str) -> None:
        """Delete in-memory state and UC bundle.json."""
        self.delete_thread(thread_id)
        try:
            await asyncio.to_thread(self._files.delete, self._bundle_path)
        except (NotFound, ResourceDoesNotExist):
            pass
        except DatabricksError as e:
            logger.warning("[bundle] adelete_thread failed: %s", e)
