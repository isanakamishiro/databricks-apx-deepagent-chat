# ボリュームエクスプローラー 実装計画

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** チャット入力欄内にボリュームエクスプローラーを追加し、カタログ→スキーマ→ボリュームの3階層ツリーからパスを選択できるようにする。

**Architecture:** バックエンドに3つの遅延ロード用エンドポイントを追加し、フロントエンドでは `primitives-base-files` ベースのツリービューを持つ `VolumeExplorer` コンポーネントを新規作成。既存の `settings-dialog.tsx` は廃止する。

**Tech Stack:** FastAPI + Databricks SDK (Python)、React + TypeScript + animate-ui/primitives-base-files + shadcn Dialog

---

## ファイル構成

| 操作 | ファイル |
|------|---------|
| 新規作成 | `src/apx_deepagent_chat/backend/routers/volumes.py` |
| 変更 | `src/apx_deepagent_chat/backend/router.py` |
| 変更 | `src/apx_deepagent_chat/ui/components/animate-ui/primitives-base-files.tsx` (import修正) |
| 変更 | `src/apx_deepagent_chat/ui/components/animate-ui/primitives-base-accordion.tsx` (import修正) |
| 新規作成 | `src/apx_deepagent_chat/ui/components/chat/volume-explorer.tsx` |
| 変更 | `src/apx_deepagent_chat/ui/routes/_sidebar/chat.index.tsx` |
| 変更 | `src/apx_deepagent_chat/ui/routes/_sidebar/chat.$threadId.tsx` |
| 削除 | `src/apx_deepagent_chat/ui/components/chat/settings-dialog.tsx` |

---

## Chunk 1: バックエンド + animate-ui インポート修正

### Task 1: animate-ui コンポーネントの import パス修正

**Files:**
- Modify: `src/apx_deepagent_chat/ui/components/animate-ui/primitives-base-accordion.tsx`
- Modify: `src/apx_deepagent_chat/ui/components/animate-ui/primitives-base-files.tsx`

**背景:** animate-ui コンポーネントは `@/lib/get-strict-context`・`@/hooks/use-controlled-state` を参照しているが、実際のファイルは `@/lib/lib-get-strict-context`・`@/hooks/hooks-use-controlled-state` という名前で存在している。また `primitives-base-files.tsx` のネスト参照も修正が必要。

- [ ] **Step 1: `primitives-base-accordion.tsx` の import を修正**

  対象行（ファイル先頭付近）:
  ```typescript
  // 修正前
  import { getStrictContext } from '@/lib/get-strict-context';
  import { useControlledState } from '@/hooks/use-controlled-state';

  // 修正後
  import { getStrictContext } from '@/lib/lib-get-strict-context';
  import { useControlledState } from '@/hooks/hooks-use-controlled-state';
  ```

- [ ] **Step 2: `primitives-base-files.tsx` の import を修正**

  対象行:
  ```typescript
  // 修正前
  import { ... } from '@/components/animate-ui/primitives/effects/highlight';
  import { ... } from '@/components/animate-ui/primitives/base/accordion';
  import { getStrictContext } from '@/lib/get-strict-context';
  import { useControlledState } from '@/hooks/use-controlled-state';

  // 修正後
  import { ... } from '@/components/animate-ui/primitives-effects-highlight';
  import { ... } from '@/components/animate-ui/primitives-base-accordion';
  import { getStrictContext } from '@/lib/lib-get-strict-context';
  import { useControlledState } from '@/hooks/hooks-use-controlled-state';
  ```

- [ ] **Step 3: `apx check` を実行してエラーがないことを確認**

  MCP tool: `mcp__apx__check` with `app_path: "/home/isanak/projects/apx-deepagent-chat"`

  Expected: animate-ui 関連の import エラーがなくなること

---

### Task 2: バックエンド volumes ルーター作成

**Files:**
- Create: `src/apx_deepagent_chat/backend/routers/volumes.py`

- [ ] **Step 1: `volumes.py` を作成**

  ```python
  from fastapi import APIRouter, Query
  from pydantic import BaseModel

  from ..core import Dependencies

  router = APIRouter()


  class CatalogOut(BaseModel):
      name: str


  class SchemaOut(BaseModel):
      name: str


  class VolumeOut(BaseModel):
      name: str


  @router.get("/volumes/catalogs", operation_id="listCatalogs", response_model=list[CatalogOut])
  async def list_catalogs(ws: Dependencies.UserClient) -> list[CatalogOut]:
      return [CatalogOut(name=c.name) for c in ws.catalogs.list() if c.name]


  @router.get("/volumes/schemas", operation_id="listSchemas", response_model=list[SchemaOut])
  async def list_schemas(
      ws: Dependencies.UserClient,
      catalog: str = Query(...),
  ) -> list[SchemaOut]:
      return [SchemaOut(name=s.name) for s in ws.schemas.list(catalog_name=catalog) if s.name]


  @router.get("/volumes/volumes", operation_id="listVolumes", response_model=list[VolumeOut])
  async def list_volumes(
      ws: Dependencies.UserClient,
      catalog: str = Query(...),
      schema: str = Query(...),
  ) -> list[VolumeOut]:
      return [
          VolumeOut(name=v.name)
          for v in ws.volumes.list(catalog_name=catalog, schema_name=schema)
          if v.name
      ]
  ```

  **注意:** `router = APIRouter()` は prefix なし（`/api` プレフィックスはアプリレベルで追加）。`ws: Dependencies.UserClient` は必ず Query params より前に置く（`files.py` L44 のパターン: `async def files_list(request: Request, ws: Dependencies.UserClient, path: str = Query("/"))` に倣う）。

---

### Task 3: ルーターを登録

**Files:**
- Modify: `src/apx_deepagent_chat/backend/router.py`

- [ ] **Step 1: `volumes_router` をインポートして登録**

  ```python
  # 追加するインポート
  from .routers.volumes import router as volumes_router

  # 追加する行（既存の include_router の後）
  router.include_router(volumes_router)
  ```

  完成後の `router.py`:
  ```python
  from databricks.sdk.service.iam import User as UserOut

  from .core import Dependencies, create_router
  from .models import VersionOut
  from .routers.chat_history import router as chat_history_router
  from .routers.config import router as config_router
  from .routers.files import router as files_router
  from .routers.volumes import router as volumes_router

  router = create_router()


  @router.get("/version", response_model=VersionOut, operation_id="version")
  async def version():
      return VersionOut.from_metadata()


  @router.get("/current-user", response_model=UserOut, operation_id="currentUser")
  def me(user_ws: Dependencies.UserClient):
      return user_ws.current_user.me()

  router.include_router(config_router)
  router.include_router(chat_history_router)
  router.include_router(files_router)
  router.include_router(volumes_router)
  ```

- [ ] **Step 2: `apx check` でバックエンドエラーがないことを確認**

  MCP tool: `mcp__apx__check` with `app_path: "/home/isanak/projects/apx-deepagent-chat"`

  Expected: Python type check errors なし

- [ ] **Step 3: コミット**

  ```bash
  git add src/apx_deepagent_chat/backend/routers/volumes.py \
          src/apx_deepagent_chat/backend/router.py \
          src/apx_deepagent_chat/ui/components/animate-ui/primitives-base-accordion.tsx \
          src/apx_deepagent_chat/ui/components/animate-ui/primitives-base-files.tsx \
          src/apx_deepagent_chat/ui/hooks/hooks-use-controlled-state.ts \
          src/apx_deepagent_chat/ui/lib/lib-get-strict-context.ts
  git commit -m "feat(backend): ボリューム一覧API追加 + animate-ui import修正"
  ```

---

## Chunk 2: フロントエンド — VolumeExplorer コンポーネントと統合

### Task 4: VolumeExplorer コンポーネント作成

**Files:**
- Create: `src/apx_deepagent_chat/ui/components/chat/volume-explorer.tsx`

- [ ] **Step 1: `volume-explorer.tsx` を作成**

  ```tsx
  import { useState } from 'react';
  import { ChevronRight, ChevronDown, Database, Folder, FolderOpen, HardDrive } from 'lucide-react';
  import { Button } from '@/components/ui/button';
  import { Skeleton } from '@/components/ui/skeleton';
  import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogFooter,
  } from '@/components/ui/dialog';
  import {
    Files,
    FolderItem,
    FolderHeader,
    FolderTrigger,
    FolderPanel,
    FolderIcon,
    FolderLabel,
    FileHighlight,
    File,
    FileLabel,
  } from '@/components/animate-ui/primitives-base-files';
  import { cn } from '@/lib/utils';

  type LoadState = 'idle' | 'loading' | 'loaded' | 'error';

  type Entry = { name: string };

  type VolumeExplorerProps = {
    value: string;
    onSelect: (path: string) => void;
  };

  export function VolumeExplorer({ value, onSelect }: VolumeExplorerProps) {
    const [open, setOpen] = useState(false);
    const [pendingPath, setPendingPath] = useState(value);

    const [catalogs, setCatalogs] = useState<Entry[]>([]);
    const [catalogState, setCatalogState] = useState<LoadState>('idle');
    const [schemas, setSchemas] = useState<Record<string, { state: LoadState; data: Entry[] }>>({});
    const [volumes, setVolumes] = useState<Record<string, { state: LoadState; data: Entry[] }>>({});

    const volumeName = value ? value.split('/').pop() : undefined;

    const loadCatalogs = async () => {
      if (catalogState !== 'idle') return;
      setCatalogState('loading');
      try {
        const res = await fetch('/api/volumes/catalogs');
        if (!res.ok) throw new Error('Failed');
        const data: Entry[] = await res.json();
        setCatalogs(data);
        setCatalogState('loaded');
      } catch {
        setCatalogState('error');
      }
    };

    const loadSchemas = async (catalog: string) => {
      if (schemas[catalog]?.state === 'loaded' || schemas[catalog]?.state === 'loading') return;
      setSchemas((p) => ({ ...p, [catalog]: { state: 'loading', data: [] } }));
      try {
        const res = await fetch(`/api/volumes/schemas?catalog=${encodeURIComponent(catalog)}`);
        if (!res.ok) throw new Error('Failed');
        const data: Entry[] = await res.json();
        setSchemas((p) => ({ ...p, [catalog]: { state: 'loaded', data } }));
      } catch {
        setSchemas((p) => ({ ...p, [catalog]: { state: 'error', data: [] } }));
      }
    };

    const loadVolumes = async (catalog: string, schema: string) => {
      const key = `${catalog}/${schema}`;
      if (volumes[key]?.state === 'loaded' || volumes[key]?.state === 'loading') return;
      setVolumes((p) => ({ ...p, [key]: { state: 'loading', data: [] } }));
      try {
        const res = await fetch(
          `/api/volumes/volumes?catalog=${encodeURIComponent(catalog)}&schema=${encodeURIComponent(schema)}`
        );
        if (!res.ok) throw new Error('Failed');
        const data: Entry[] = await res.json();
        setVolumes((p) => ({ ...p, [key]: { state: 'loaded', data } }));
      } catch {
        setVolumes((p) => ({ ...p, [key]: { state: 'error', data: [] } }));
      }
    };

    const handleDialogOpen = (isOpen: boolean) => {
      setOpen(isOpen);
      if (isOpen) {
        setPendingPath(value);
        loadCatalogs();
      }
    };

    return (
      <>
        <Button
          variant={volumeName ? 'outline' : 'ghost'}
          size="sm"
          className={cn('h-7 text-xs gap-1', volumeName && 'border-primary text-primary')}
          onClick={() => handleDialogOpen(true)}
        >
          <Database size={12} />
          {volumeName ?? 'Volume'}
        </Button>
        <Dialog open={open} onOpenChange={handleDialogOpen}>
          <DialogContent className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle>ボリュームを選択</DialogTitle>
            </DialogHeader>

            <div className="min-h-[200px] max-h-[350px] overflow-y-auto border rounded-md p-2 text-sm">
              {catalogState === 'loading' && (
                <div className="space-y-2 p-2">
                  <Skeleton className="h-5 w-full" />
                  <Skeleton className="h-5 w-3/4" />
                  <Skeleton className="h-5 w-5/6" />
                </div>
              )}
              {catalogState === 'error' && (
                <p className="text-destructive p-2 text-xs">カタログの取得に失敗しました</p>
              )}
              {catalogState === 'loaded' && catalogs.length === 0 && (
                <p className="text-muted-foreground p-2 text-xs">アクセス可能なカタログがありません</p>
              )}
              {catalogState === 'loaded' && catalogs.length > 0 && (
                <Files>
                  {catalogs.map((cat) => (
                    <FolderItem key={cat.name} value={cat.name}>
                      <FolderHeader>
                        <FolderTrigger
                          className="flex w-full items-center gap-1.5 rounded px-2 py-1 text-left hover:bg-accent"
                          onClick={() => loadSchemas(cat.name)}
                        >
                          <FolderIcon
                            closeIcon={<ChevronRight size={12} />}
                            openIcon={<ChevronDown size={12} />}
                          />
                          <FolderIcon
                            closeIcon={<Folder size={13} className="text-yellow-500" />}
                            openIcon={<FolderOpen size={13} className="text-yellow-500" />}
                          />
                          <FolderLabel>{cat.name}</FolderLabel>
                        </FolderTrigger>
                      </FolderHeader>
                      <FolderPanel className="ml-5 border-l pl-2">
                        {schemas[cat.name]?.state === 'loading' && (
                          <div className="space-y-1 py-1">
                            <Skeleton className="h-4 w-full" />
                            <Skeleton className="h-4 w-3/4" />
                          </div>
                        )}
                        {schemas[cat.name]?.state === 'error' && (
                          <p className="text-destructive py-1 text-xs">取得に失敗しました</p>
                        )}
                        {schemas[cat.name]?.state === 'loaded' && schemas[cat.name].data.length === 0 && (
                          <p className="text-muted-foreground py-1 text-xs">スキーマがありません</p>
                        )}
                        {schemas[cat.name]?.state === 'loaded' &&
                          schemas[cat.name].data.map((sc) => (
                            <FolderItem key={sc.name} value={`${cat.name}/${sc.name}`}>
                              <FolderHeader>
                                <FolderTrigger
                                  className="flex w-full items-center gap-1.5 rounded px-2 py-1 text-left hover:bg-accent"
                                  onClick={() => loadVolumes(cat.name, sc.name)}
                                >
                                  <FolderIcon
                                    closeIcon={<ChevronRight size={12} />}
                                    openIcon={<ChevronDown size={12} />}
                                  />
                                  <FolderLabel>{sc.name}</FolderLabel>
                                </FolderTrigger>
                              </FolderHeader>
                              <FolderPanel className="ml-5 border-l pl-2">
                                {(() => {
                                  const key = `${cat.name}/${sc.name}`;
                                  const vs = volumes[key];
                                  if (vs?.state === 'loading')
                                    return (
                                      <div className="space-y-1 py-1">
                                        <Skeleton className="h-4 w-full" />
                                        <Skeleton className="h-4 w-3/4" />
                                      </div>
                                    );
                                  if (vs?.state === 'error')
                                    return <p className="text-destructive py-1 text-xs">取得に失敗しました</p>;
                                  if (vs?.state === 'loaded' && vs.data.length === 0)
                                    return (
                                      <p className="text-muted-foreground py-1 text-xs">ボリュームがありません</p>
                                    );
                                  return vs?.data.map((vol) => {
                                    const path = `/Volumes/${cat.name}/${sc.name}/${vol.name}`;
                                    const isSelected = pendingPath === path;
                                    return (
                                      <FileHighlight key={vol.name}>
                                        <File
                                          className={cn(
                                            'flex cursor-pointer items-center gap-1.5 rounded px-2 py-1 hover:bg-accent',
                                            isSelected && 'bg-primary/10 font-medium text-primary'
                                          )}
                                          onClick={() => setPendingPath(path)}
                                        >
                                          <HardDrive size={13} />
                                          <FileLabel>{vol.name}</FileLabel>
                                          {isSelected && <span className="ml-auto text-xs">✓</span>}
                                        </File>
                                      </FileHighlight>
                                    );
                                  });
                                })()}
                              </FolderPanel>
                            </FolderItem>
                          ))}
                      </FolderPanel>
                    </FolderItem>
                  ))}
                </Files>
              )}
            </div>

            {pendingPath && (
              <p className="truncate text-xs text-green-600">📍 {pendingPath}</p>
            )}

            <DialogFooter>
              <Button variant="outline" onClick={() => setOpen(false)}>
                キャンセル
              </Button>
              <Button
                onClick={() => {
                  onSelect(pendingPath);
                  setOpen(false);
                }}
                disabled={!pendingPath}
              >
                選択
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </>
    );
  }
  ```

- [ ] **Step 2: `apx check` でコンポーネント単体の型エラーがないことを確認**

  MCP tool: `mcp__apx__check`

  Expected: `volume-explorer.tsx` に型エラーなし。

  **FolderTrigger の `onClick` で型エラーが出た場合のフォールバック:**
  `AccordionTriggerProps` が `onClick` を受け付けない場合は、FolderTrigger の中に `<span onPointerDown={() => loadSchemas(cat.name)}>` でラップするか、または `FolderHeader` 自体に `onClick` ハンドラを追加する:
  ```tsx
  <FolderHeader onClick={() => loadSchemas(cat.name)}>
    <FolderTrigger className="...">
      ...
    </FolderTrigger>
  </FolderHeader>
  ```

---

### Task 5: chat.index.tsx を更新

**Files:**
- Modify: `src/apx_deepagent_chat/ui/routes/_sidebar/chat.index.tsx`

- [ ] **Step 1: import を差し替え**

  ```tsx
  // 削除
  import { SettingsDialog } from "@/components/chat/settings-dialog";

  // 追加
  import { VolumeExplorer } from "@/components/chat/volume-explorer";
  ```

- [ ] **Step 2: `handleSaveSettings` を `handleVolumeSelect` に改名**

  ```tsx
  // 変更前
  const handleSaveSettings = (vp: string) => {
    setVolumePath(vp);
    localStorage.setItem(STORAGE_KEY_VOLUME, vp);
  };

  // 変更後
  const handleVolumeSelect = (vp: string) => {
    setVolumePath(vp);
    localStorage.setItem(STORAGE_KEY_VOLUME, vp);
  };
  ```

- [ ] **Step 3: JSX を更新 — SettingsDialog を VolumeExplorer に差し替え + パス表示を追加**

  `PromptInput` を囲む `<div className="w-full max-w-2xl">` を以下に変更:
  ```tsx
  <div className="w-full max-w-2xl">
    <PromptInput onSubmit={handleFormSubmit}>
      <PromptInputBody>
        <PromptInputTextarea
          placeholder="メッセージを入力... (Enter で送信、Shift+Enter で改行)"
        />
      </PromptInputBody>
      <PromptInputFooter>
        <PromptInputTools>
          {availableModels.length > 0 && (
            <PromptInputSelect
              value={selectedModel}
              onValueChange={handleModelChange}
            >
              <PromptInputSelectTrigger className="h-7 text-xs max-w-[180px]">
                <PromptInputSelectValue placeholder="モデル選択" />
              </PromptInputSelectTrigger>
              <PromptInputSelectContent>
                {availableModels.map((m) => (
                  <PromptInputSelectItem key={m} value={m}>
                    {m}
                  </PromptInputSelectItem>
                ))}
              </PromptInputSelectContent>
            </PromptInputSelect>
          )}
          <VolumeExplorer value={volumePath} onSelect={handleVolumeSelect} />
        </PromptInputTools>
        <PromptInputSubmit />
      </PromptInputFooter>
    </PromptInput>
    {volumePath ? (
      <p className="mt-1 px-1 text-xs text-green-600">📂 {volumePath}</p>
    ) : (
      <p className="mt-1 px-1 text-xs text-muted-foreground">📂 ボリュームが未設定です</p>
    )}
  </div>
  ```

---

### Task 6: chat.$threadId.tsx を更新

**Files:**
- Modify: `src/apx_deepagent_chat/ui/routes/_sidebar/chat.$threadId.tsx`

- [ ] **Step 1: import を差し替え**

  ```tsx
  // 削除
  import { SettingsDialog } from "@/components/chat/settings-dialog";

  // 追加
  import { VolumeExplorer } from "@/components/chat/volume-explorer";
  ```

- [ ] **Step 2: `ChatContentProps` の `onSaveSettings` を `onVolumeSelect` に改名**

  ```tsx
  // 変更前
  type ChatContentProps = {
    ...
    onSaveSettings: (vp: string) => void;
    ...
  };

  // 変更後
  type ChatContentProps = {
    ...
    onVolumeSelect: (vp: string) => void;
    ...
  };
  ```

- [ ] **Step 3: `ChatContent` 関数の引数を更新**

  ```tsx
  // 変更前
  function ChatContent({
    ...
    onSaveSettings,
    ...
  }: ChatContentProps) {

  // 変更後
  function ChatContent({
    ...
    onVolumeSelect,
    ...
  }: ChatContentProps) {
  ```

- [ ] **Step 4: JSX 内の `SettingsDialog` を `VolumeExplorer` に差し替え**

  `PromptInputTools` 内:
  ```tsx
  // 変更前
  <SettingsDialog
    volumePath={volumePath}
    onSave={onSaveSettings}
  />

  // 変更後
  <VolumeExplorer value={volumePath} onSelect={onVolumeSelect} />
  ```

- [ ] **Step 5: `ChatPage` → `ChatContent` の prop を更新**

  ```tsx
  // 変更前
  onSaveSettings={handleSaveSettings}

  // 変更後
  onVolumeSelect={handleSaveSettings}
  ```

- [ ] **Step 6: 入力欄下部にボリュームパス表示を追加**

  `ChatContent` 内の既存コード（現在: `<div className="max-w-2xl mx-auto">{promptInput}</div>`）を変更:
  ```tsx
  // 変更前（chat.$threadId.tsx 現行コード）
  <div className="max-w-2xl mx-auto">{promptInput}</div>

  // 変更後
  <div className="max-w-2xl mx-auto">
    {promptInput}
    {volumePath ? (
      <p className="mt-1 px-1 text-xs text-green-600">📂 {volumePath}</p>
    ) : (
      <p className="mt-1 px-1 text-xs text-muted-foreground">📂 ボリュームが未設定です</p>
    )}
  </div>
  ```

---

### Task 7: settings-dialog.tsx を削除し、型チェック・動作確認

**Files:**
- Delete: `src/apx_deepagent_chat/ui/components/chat/settings-dialog.tsx`

- [ ] **Step 1: `settings-dialog.tsx` を削除**

  ```bash
  rm src/apx_deepagent_chat/ui/components/chat/settings-dialog.tsx
  ```

- [ ] **Step 2: `apx check` でフロントエンド全体の型エラーがないことを確認**

  MCP tool: `mcp__apx__check`

  Expected: TypeScript / Python エラーなし。`SettingsDialog` の残存参照がないこと。

- [ ] **Step 3: dev サーバーを起動して動作確認（playwright使用）**

  MCP tool: `mcp__apx__start` で URL を取得。

  playwright で以下を確認:
  1. チャット画面 (`/`) に「Volume」ボタンが表示される
  2. 「Volume」ボタンをクリックするとダイアログが開く（カタログロード開始）
  3. カタログ取得後、ツリーに表示される
  4. カタログを展開するとスキーマが遅延ロードされる
  5. ボリューム選択後「選択」ボタンをクリックするとダイアログが閉じ、パスが入力欄下部に緑色で表示される
  6. ページリロード後もパスが復元される
  7. チャット（`/chat/$threadId`）画面でも同様に動作する
  8. 旧「設定」アイコン（歯車）が表示されないこと

  スクリーンショットを `/screenshots/` に保存する。

- [ ] **Step 4: コミット**

  ```bash
  git add src/apx_deepagent_chat/ui/components/chat/volume-explorer.tsx \
          src/apx_deepagent_chat/ui/routes/_sidebar/chat.index.tsx \
          src/apx_deepagent_chat/ui/routes/_sidebar/chat.$threadId.tsx
  git rm src/apx_deepagent_chat/ui/components/chat/settings-dialog.tsx
  git commit -m "feat(ui): ボリュームエクスプローラー追加・設定ダイアログ廃止"
  ```

---

## 検証チェックリスト

| 確認項目 | 方法 |
|---------|------|
| `GET /api/volumes/catalogs` が 200 を返す | playwright / curl |
| `GET /api/volumes/schemas?catalog=X` が 200 を返す | playwright / curl |
| `GET /api/volumes/volumes?catalog=X&schema=Y` が 200 を返す | playwright / curl |
| chat.index でVolumeボタン表示 | playwright screenshot |
| ダイアログでツリー表示 (3階層) | playwright screenshot |
| ボリューム選択後パスが入力欄下部に表示 | playwright screenshot |
| リロード後パスが復元 | playwright |
| chat.$threadId でも同様に動作 | playwright screenshot |
| 設定ダイアログ（歯車）が消えている | playwright screenshot |
| `apx check` エラーなし | MCP tool |
