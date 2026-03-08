from pathlib import Path

app_name = "apx-deepagent-chat"
app_entrypoint = "apx_deepagent_chat.backend.app:app"
app_slug = "apx_deepagent_chat"
api_prefix = "/api"
dist_dir = Path(__file__).parent / "__dist__"