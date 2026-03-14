# APX DeepAgent Chat

A multi-agent chat application running on Databricks, built with [apx](https://databricks-solutions.github.io/apx/). Provides LLM-powered web research and automatic HTML report generation.

[日本語版はこちら](README.ja.md)

## Features

- **Multi-agent orchestration**: Web research agent and report generation agent work in tandem
- **Multiple LLM models**: Choose from 5 available models
- **Automatic report generation**: Transforms web research results into polished HTML reports
- **Databricks UC Volume integration**: Saves research results and reports to Databricks storage
- **Chat history management**: Save and browse past conversations
- **MLflow integration**: Agent trace recording and experiment management

## Architecture

| Layer | Technology |
|-------|------------|
| Backend | Python + FastAPI |
| Frontend | React 19 + TypeScript + shadcn/ui |
| AI | Databricks Model Serving + LangChain + deepagents |
| Storage | Databricks UC Volume |
| Observability | MLflow (tracing & experiment tracking) |

## Sub-agents

| Agent | Role |
|-------|------|
| `web_researcher` | Performs web search and research, saves results as Markdown to UC Volume |
| `final_report_creator` | Transforms Markdown drafts into polished final HTML reports |

## Prerequisites

- Databricks Workspace with access to Model Serving endpoints
- [apx CLI](https://github.com/databricks-solutions/apx) installed
- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- [bun](https://bun.sh/) (frontend package manager)

## Setup

```bash
# Clone the repository
git clone https://github.com/your-org/apx-deepagent-chat.git
cd apx-deepagent-chat

# Install dependencies
uv sync
cd src/apx_deepagent_chat/ui && bun install && cd -

# Start the development server
apx dev start
```

### Environment Variables (local development)

Copy `.env.example` to `.env` and fill in your values:

```
DATABRICKS_CONFIG_PROFILE=<your-profile>
MLFLOW_EXPERIMENT_ID=<your-experiment-id>
```

In production (Databricks Apps), a service principal is used automatically.

## Development Commands

```bash
# Start all dev servers
apx dev start

# View logs
apx dev logs

# Stream logs in real time
apx dev logs -f

# Type check (TypeScript + Python)
apx dev check

# Stop all servers
apx dev stop
```

## Testing

```bash
# すべてのテストを実行 (統合テストを除く)
uv run pytest -m "not integration"

# ユニットテストのみ
uv run pytest tests/unit/

# API テストのみ
uv run pytest tests/api/

# カバレッジレポートを表示 (デフォルトで自動付与)
uv run pytest -m "not integration" --cov-report=html

# 統合テスト (実 Databricks 接続が必要)
export TEST_VOLUME_PATH=/Volumes/<catalog>/<schema>/<volume>
uv run pytest -m integration
```

## Deployment

```bash
# Production build
apx build

# Deploy to Databricks
databricks bundle deploy -p <your-profile>
```

### Deployment Variables

The following variables are required in `databricks.yml`:

| Variable | Description |
|----------|-------------|
| `experiment_id` | MLflow experiment ID |
| `volume_full_name` | UC Volume for data storage (e.g. `workspace.default.my-volume`) |
| `mlflow_tracking_volume_full_name` | UC Volume for MLflow trace storage |

You can also set them as environment variables:

```bash
export BUNDLE_VAR_experiment_id=<your-experiment-id>
export BUNDLE_VAR_volume_full_name=<your-volume>
export BUNDLE_VAR_mlflow_tracking_volume_full_name=<your-mlflow-volume>
databricks bundle deploy -p <your-profile>
```

## Project Structure

```
apx-deepagent-chat/
├── src/apx_deepagent_chat/
│   ├── backend/              # FastAPI backend
│   │   ├── app.py            # FastAPI entrypoint
│   │   ├── agent.py          # Agent logic & SSE streaming
│   │   ├── core.py           # Dependency injection & config
│   │   └── routers/          # API routes
│   ├── ui/                   # React frontend
│   │   └── routes/           # Page components
│   └── assets/               # Agent configuration
│       ├── models.yaml        # Available LLM model definitions
│       ├── subagents.yaml     # Sub-agent definitions
│       └── system_prompt.md   # System prompt
├── databricks.yml            # Databricks deployment config
└── pyproject.toml            # Python project config
```

---

<p align="center">Built with <a href="https://github.com/databricks-solutions/apx">apx</a></p>
