# APX DeepAgent Chat

Databricks上で動作するマルチエージェント型チャットアプリ。LLMを使ったWebリサーチと自動HTMLレポート生成を提供します。

## 主な機能

- **マルチエージェント対応**: Web調査エージェントとレポート生成エージェントが連携
- **複数LLMモデル**: 5種類のモデルを選択して利用可能
- **自動レポート生成**: Web調査結果をポーランドされたHTMLレポートに変換
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
| `final_report_creator` | Markdownドラフトをポーランドされた最終HTMLレポートに変換 |

## 前提条件

- Databricks Workspace（Model Servingエンドポイントへのアクセス）
- [apx CLI](https://github.com/databricks-solutions/apx) インストール済み
- Python 3.11+
- [uv](https://docs.astral.sh/uv/)（Pythonパッケージマネージャ）
- [bun](https://bun.sh/)（フロントエンドパッケージマネージャ）

## セットアップ

```bash
# リポジトリのクローン
git clone https://github.com/your-org/apx-deepagent-chat.git
cd apx-deepagent-chat

# 依存関係のインストール
uv sync
cd src/apx_deepagent_chat/ui && bun install && cd -

# 開発サーバの起動
apx dev start
```

### 環境変数（ローカル開発時）

プロジェクトルートに `.env` ファイルを作成してください：

```
DATABRICKS_HOST=https://your-workspace.azuredatabricks.net
DATABRICKS_TOKEN=your-personal-access-token
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

# 型チェック
apx dev check

# サーバの停止
apx dev stop
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
│   ├── backend/          # FastAPI バックエンド
│   │   ├── app.py        # FastAPIエントリポイント
│   │   ├── agent.py      # エージェント処理・SSEストリーミング
│   │   ├── core.py       # 依存性注入・設定
│   │   └── routers/      # APIルート
│   ├── ui/               # React フロントエンド
│   │   └── routes/       # ページコンポーネント
│   └── assets/           # エージェント設定
│       ├── models.yaml   # 利用可能なLLMモデル定義
│       ├── subagents.yaml # サブエージェント定義
│       └── system_prompt.md # システムプロンプト
├── databricks.yml        # Databricksデプロイ設定
└── pyproject.toml        # Pythonプロジェクト設定
```

---

<p align="center">Built with <a href="https://github.com/databricks-solutions/apx">apx</a></p>
