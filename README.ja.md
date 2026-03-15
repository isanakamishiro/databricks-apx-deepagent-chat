# APX DeepAgent Chat

Databricks上で動作するマルチエージェント型チャットアプリ。[apx](https://databricks-solutions.github.io/apx/) を使って構築されています。LLMを使ったWebリサーチ、コンテンツ執筆、自動HTMLレポート生成を提供します。

[English README](README.md)

## 主な機能

- **マルチエージェント対応**: Web調査・コンテンツ執筆・レポート生成エージェントが連携
- **複数LLMモデル**: 5種類のモデルを選択して利用可能
- **コンテンツ執筆・翻訳**: オリジナル記事の執筆やWebコンテンツのQiita形式Markdownへの翻訳
- **自動レポート生成**: 調査結果をポーランドされたHTMLレポートに変換
- **Databricks UC Volume連携**: 調査結果・レポートをDatabricksのストレージに保存
- **チャット履歴管理**: 過去の会話の保存・参照
- **MLflow統合**: エージェントのトレース記録と実験管理

## アーキテクチャ

| レイヤー | 技術 |
|----------|------|
| Backend | Python + FastAPI |
| Frontend | React 19 + TypeScript + shadcn/ui |
| AI基盤 | Databricks Model Serving + LangChain + deepagents |
| ストレージ | Databricks UC Volume |
| 可観測性 | MLflow（トレース・実験管理） |

## サブエージェント

| エージェント | 役割 |
|--------------|------|
| `web_researcher` | Web検索・調査を実行し、結果をMarkdown形式でUC Volumeに保存 |
| `content_writer` | URLの翻訳やオリジナル記事執筆を担当し、Qiita形式Markdownで保存 |
| `final_report_creator` | Markdownドラフトをポーランドされた最終HTMLレポートに変換 |

## クイックスタート: GitHub → Databricks Apps

### Step 1: 前提条件の確認

- Model Servingエンドポイントへのアクセス権を持つDatabricks Workspace
- [Databricks CLI](https://docs.databricks.com/dev-tools/cli/databricks-cli.html) のインストールと認証設定（`databricks auth login`）
- [apx CLI](https://github.com/databricks-solutions/apx) のインストール
- Python 3.11+、[uv](https://docs.astral.sh/uv/)、[bun](https://bun.sh/) のインストール

### Step 2: リポジトリのクローン

```bash
git clone https://github.com/isanakamishiro/databricks-apx-deepagent-chat.git
cd apx-deepagent-chat
```

### Step 3: UC VolumesとMLflow実験の作成

Databricks Workspace上で2つのUC Volume（データ保存用・MLflow追跡用）とMLflow実験を作成し、実験IDを控えておきます。

### Step 4: Bundle変数の設定

```bash
export BUNDLE_VAR_experiment_id=<mlflow-experiment-id>
export BUNDLE_VAR_volume_full_name=<catalog>.<schema>.<volume>
export BUNDLE_VAR_mlflow_tracking_volume_full_name=<catalog>.<schema>.<mlflow-volume>
```

### Step 5: デプロイ

```bash
databricks bundle deploy -p <your-profile>
```

---

## 前提条件

- Databricks Workspace（Model Servingエンドポイントへのアクセス）
- [apx CLI](https://github.com/databricks-solutions/apx) インストール済み
- Python 3.11+
- [uv](https://docs.astral.sh/uv/)（Pythonパッケージマネージャ）
- [bun](https://bun.sh/)（フロントエンドパッケージマネージャ）

## セットアップ

```bash
# リポジトリのクローン
git clone https://github.com/isanakamishiro/databricks-apx-deepagent-chat.git
cd apx-deepagent-chat

# Python依存関係のインストール
uv sync

# 開発サーバの起動（フロントエンド依存関係も自動インストール）
apx dev start
```

### 環境変数（ローカル開発時）

`.env.example` を `.env` にコピーして値を設定してください：

```
DATABRICKS_CONFIG_PROFILE=<your-profile>
MLFLOW_EXPERIMENT_ID=<your-experiment-id>
```

本番環境（Databricks Apps）ではサービスプリンシパルが自動的に使用されます。

## 開発コマンド

```bash
# 開発サーバの起動
apx dev start

# ログの確認
apx dev logs

# ログのリアルタイム表示
apx dev logs -f

# 型チェック（TypeScript + Python）
apx dev check

# サーバの停止
apx dev stop
```

## テスト

```bash
# 全テストの実行（インテグレーションテストを除く）
uv run pytest -m "not integration"

# ユニットテストのみ
uv run pytest tests/unit/

# APIテストのみ
uv run pytest tests/api/

# カバレッジレポートの生成（デフォルトで適用済み）
uv run pytest -m "not integration" --cov-report=html

# インテグレーションテスト（Databricks接続が必要）
export TEST_VOLUME_PATH=/Volumes/<catalog>/<schema>/<volume>
uv run pytest -m integration
```

## デプロイ

```bash
# 本番ビルド
apx build

# Databricksへのデプロイ
databricks bundle deploy -p <your-profile>
```

### デプロイ時の変数設定

`databricks.yml` で以下の変数が必要です：

| 変数 | 説明 |
|------|------|
| `experiment_id` | MLflow実験のID |
| `volume_full_name` | データ保存用UC Volume名（例: `workspace.default.my-volume`） |
| `mlflow_tracking_volume_full_name` | トレース保存用UC Volume名 |

環境変数での指定も可能です：

```bash
export BUNDLE_VAR_experiment_id=<your-experiment-id>
export BUNDLE_VAR_volume_full_name=<your-volume>
export BUNDLE_VAR_mlflow_tracking_volume_full_name=<your-mlflow-volume>
databricks bundle deploy -p <your-profile>
```

## プロジェクト構成

```
apx-deepagent-chat/
├── src/apx_deepagent_chat/
│   ├── backend/              # FastAPI バックエンド
│   │   ├── app.py            # FastAPIエントリポイント
│   │   ├── agent/            # エージェント処理・SSEストリーミング
│   │   ├── core/             # 依存性注入・設定
│   │   ├── models.py         # Pydanticモデル
│   │   └── routers/          # APIルート
│   │       ├── chat_history.py
│   │       ├── files.py
│   │       ├── system.py
│   │       └── volumes.py
│   ├── ui/                   # React フロントエンド
│   │   └── routes/           # ページコンポーネント
│   └── assets/               # エージェント設定
│       ├── models.yaml        # 利用可能なLLMモデル定義
│       ├── subagents.yaml     # サブエージェント定義
│       ├── system_prompt.md   # システムプロンプト
│       ├── mcp_settings.yaml  # MCPサーバ設定
│       └── skills/           # サブエージェントスキル定義
│           └── sub/
│               ├── web-researcher/
│               ├── content-translator/
│               ├── article-writer/
│               └── final-report-creator/
├── databricks.yml            # Databricksデプロイ設定
└── pyproject.toml            # Pythonプロジェクト設定
```

---

<p align="center">Built with <a href="https://github.com/databricks-solutions/apx">apx</a></p>
