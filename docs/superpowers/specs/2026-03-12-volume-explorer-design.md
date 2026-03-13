# ボリュームエクスプローラー設計仕様

**日付:** 2026-03-12
**ステータス:** 承認済み

---

## 概要

チャット画面にてボリュームパスをUIから選択できるようにする。ユーザーがアクセス可能なカタログ・スキーマ・ボリュームを3階層のツリーで表示し、1つ選択できる。既存の設定ダイアログ（`settings-dialog.tsx`）は廃止する。

---

## 要件

### 機能要件
- チャット入力欄内、モデルセレクタの右隣に「Volume」ボタンを配置する
- ボタンをクリックするとボリュームエクスプローラーダイアログが開く
- エクスプローラーはカタログ→スキーマ→ボリュームの3階層ツリー形式で表示する
- ツリーは遅延ロード：カタログ展開時にスキーマを取得、スキーマ展開時にボリュームを取得
- ボリュームを選択後「選択」ボタンで確定する
- 選択したボリュームパス（`/Volumes/{catalog}/{schema}/{volume}`）をチャット入力欄の下部に表示する
- 既存の設定ダイアログ（`settings-dialog.tsx`）は廃止する
- ボリュームが未設定の場合、入力欄下部に案内テキストを表示する
- 設定済みの場合、ボタンにボリューム名を表示し、パスを緑色で表示する

### 非機能要件
- `primitives-base-files`（`animate-ui`）コンポーネントを使用したツリービュー
- ボリューム一覧取得にはユーザー認証（`UserClient`）を使用する
- `chat.index.tsx` と `chat.$threadId.tsx` の両ページに適用する

---

## アーキテクチャ

### バックエンド

新規ファイル: `src/apx_deepagent_chat/backend/routers/volumes.py`

**Pydantic モデル:**
```python
class CatalogOut(BaseModel):
    name: str

class SchemaOut(BaseModel):
    name: str

class VolumeOut(BaseModel):
    name: str
```

**3つのエンドポイントを追加（遅延ロード対応）：**

```python
@router.get("/volumes/catalogs", operation_id="listCatalogs", response_model=list[CatalogOut])
async def list_catalogs(ws: Dependencies.UserClient):
    return [CatalogOut(name=c.name) for c in ws.catalogs.list()]

@router.get("/volumes/schemas", operation_id="listSchemas", response_model=list[SchemaOut])
async def list_schemas(catalog: str, ws: Dependencies.UserClient):
    return [SchemaOut(name=s.name) for s in ws.schemas.list(catalog_name=catalog)]

@router.get("/volumes/volumes", operation_id="listVolumes", response_model=list[VolumeOut])
async def list_volumes(catalog: str, schema: str, ws: Dependencies.UserClient):
    return [VolumeOut(name=v.name) for v in ws.volumes.list(catalog_name=catalog, schema_name=schema)]
```

- Databricks SDK `WorkspaceClient` (`UserClient`、OBO トークン必須) を使用
- `router.py` にボリュームルーターを追加
- **注意:** `UserClient` は `X-Forwarded-Access-Token` ヘッダーが必須。Databricks Apps 環境以外では動作しない

### フロントエンド

#### 新規コンポーネント: `VolumeExplorer`

`src/apx_deepagent_chat/ui/components/chat/volume-explorer.tsx`

責務：
- 「Volume」ボタン（未設定: グレー、設定済み: ボリューム名をハイライト表示）
- shadcn `Dialog` でモーダルを表示
- `primitives-base-files` の `Files / FolderItem / FolderHeader / FolderTrigger / FolderPanel / FolderIcon / FolderLabel / FileHighlight / File / FileLabel` で3階層ツリーを実装
- **遅延ロード:** 各カタログの `FolderTrigger` の `onClick` でスキーマを取得、各スキーマの `FolderTrigger` の `onClick` でボリュームを取得する（`Files` の `onOpenChange` は全展開ノードリストを返すため、差分計算が必要になり複雑。代わりに個別ノードの `onClick` で未ロード時のみ fetch する）
- ローディング中は `FolderPanel` 内に `Skeleton` を表示
- ダイアログ下部に選択中のフルパスをプレビュー表示
- 「選択」ボタンで `onSelect(path)` コールバックを呼び出す

```tsx
type VolumeExplorerProps = {
  value: string;                    // 現在のボリュームパス
  onSelect: (path: string) => void; // 選択確定コールバック
};
```

#### 入力欄下部のパス表示

```tsx
// VolumePathDisplay コンポーネント（または inline JSX）
{volumePath
  ? <span className="text-green-400">📂 {volumePath}</span>
  : <span className="text-muted-foreground">📂 ボリュームが未設定です</span>
}
```

#### 変更対象ファイル

| ファイル | 変更内容 |
|---------|---------|
| `chat.index.tsx` | 設定ダイアログを `VolumeExplorer` に置き換え、パス表示を追加 |
| `chat.$threadId.tsx` | 設定ダイアログを `VolumeExplorer` に置き換え、パス表示を追加。`ChatContentProps` の `onSaveSettings` は `onVolumeSelect` に改名 |
| `settings-dialog.tsx` | **廃止・削除** |

---

## データフロー

```
ユーザーがVolumeボタンをクリック
  → Dialogが開く
  → /api/volumes/catalogs を fetch（初回のみ）
  → カタログ一覧をツリー表示

カタログを展開
  → /api/volumes/schemas?catalog={name} を fetch（未ロード時のみ）
  → スキーマ一覧をサブツリーに追加

スキーマを展開
  → /api/volumes/volumes?catalog={cat}&schema={schema} を fetch（未ロード時のみ）
  → ボリューム一覧をリーフとして表示

ボリュームをクリック
  → 選択状態をハイライト
  → ダイアログ下部にフルパスをプレビュー

「選択」ボタンをクリック
  → onSelect("/Volumes/{catalog}/{schema}/{volume}")
  → ダイアログを閉じる
  → 呼び出し元で setVolumePath(path) + localStorage.setItem(STORAGE_KEY_VOLUME, path)
  → 入力欄下部にパス表示（既存の volumePath state を流用）
```

---

## エラーハンドリング

- API取得エラー時：ツリーノードにエラー状態を表示（再試行可能）
- カタログが0件：「アクセス可能なカタログがありません」テキストを表示
- ボリュームが0件のスキーマ：「ボリュームがありません」テキストを表示
- ローディング状態：展開中のフォルダに `Skeleton` を表示

---

## 検証方法

1. `apx dev start` でサーバーを起動
2. `GET /api/volumes/catalogs` が正常に返却されること
3. チャット画面でVolumeボタンが表示されること
4. ダイアログでツリーが3階層表示されること
5. ボリューム選択後、入力欄下部にパスが表示されること
6. チャット送信時に選択パスがリクエストに含まれること
7. ページリロード後もパスが復元されること
8. 既存の設定ダイアログが表示されないこと
