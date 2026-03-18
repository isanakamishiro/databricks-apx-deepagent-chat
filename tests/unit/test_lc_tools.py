"""lc_tools.py のユニットテスト."""

from unittest.mock import MagicMock, patch

from apx_deepagent_chat.backend.agent.lc_tools import (
    get_current_time,
    web_fetch,
    web_search,
)

# ─── web_search ───────────────────────────────────────────────────────────────


def test_web_search_returns_formatted_results():
    """検索結果をマークダウン形式で返す."""
    fake_results = [
        {
            "title": "記事タイトル",
            "href": "https://example.com",
            "body": "本文テキスト",
        },
    ]
    with patch("ddgs.DDGS") as mock_ddgs_cls:
        mock_ddgs_cls.return_value.text.return_value = iter(fake_results)
        result = web_search.run({"query": "テスト検索"})
    assert "### 1. 記事タイトル" in result
    assert "https://example.com" in result
    assert "本文テキスト" in result


def test_web_search_empty_results():
    """結果なし → 「見つかりませんでした」メッセージを返す."""
    with patch("ddgs.DDGS") as mock_ddgs_cls:
        mock_ddgs_cls.return_value.text.return_value = iter([])
        result = web_search.run({"query": "存在しないクエリ"})
    assert "見つかりませんでした" in result


def test_web_search_timeout_error():
    """TimeoutError → タイムアウトエラーメッセージを返す."""
    with patch("ddgs.DDGS") as mock_ddgs_cls:
        mock_ddgs_cls.return_value.text.side_effect = TimeoutError()
        result = web_search.run({"query": "任意"})
    assert "タイムアウト" in result


def test_web_search_unexpected_error():
    """予期しない例外 → 汎用エラーメッセージを返す（例外詳細はログのみ）."""
    with patch("ddgs.DDGS") as mock_ddgs_cls:
        mock_ddgs_cls.return_value.text.side_effect = RuntimeError("network error")
        result = web_search.run({"query": "任意"})
    assert "予期しないエラー" in result
    # 例外クラス名はエラーメッセージに含まれない（セキュリティのため）
    assert "RuntimeError" not in result


def test_web_search_multiple_results_numbered():
    """複数結果が番号付きで返る."""
    fake_results = [
        {"title": "結果1", "href": "https://a.com", "body": "本文1"},
        {"title": "結果2", "href": "https://b.com", "body": "本文2"},
    ]
    with patch("ddgs.DDGS") as mock_ddgs_cls:
        mock_ddgs_cls.return_value.text.return_value = iter(fake_results)
        result = web_search.run({"query": "テスト"})
    assert "### 1. 結果1" in result
    assert "### 2. 結果2" in result


def test_web_search_missing_fields():
    """タイトル・URL が欠損した結果でもクラッシュしない."""
    fake_results = [{"body": "本文のみ"}]
    with patch("ddgs.DDGS") as mock_ddgs_cls:
        mock_ddgs_cls.return_value.text.return_value = iter(fake_results)
        result = web_search.run({"query": "テスト"})
    assert "タイトルなし" in result
    assert "URLなし" in result


# ─── web_fetch ────────────────────────────────────────────────────────────────


def test_web_fetch_returns_markdown():
    """URLからMarkdownテキストを取得して返す."""
    mock_result = MagicMock()
    mock_result.text_content = "# 見出し\n本文テキスト"
    with patch("markitdown.MarkItDown") as mock_md_cls:
        mock_md_cls.return_value.convert_url.return_value = mock_result
        result = web_fetch.run({"url": "https://example.com"})
    assert "# 見出し" in result
    assert "本文テキスト" in result


def test_web_fetch_truncates_long_content():
    """max_length を超えるテキストは截断される."""
    mock_result = MagicMock()
    mock_result.text_content = "a" * 100
    with patch("markitdown.MarkItDown") as mock_md_cls:
        mock_md_cls.return_value.convert_url.return_value = mock_result
        result = web_fetch.run({"url": "https://example.com", "max_length": 10})
    assert result.endswith("... (truncated)")
    assert len(result) == len("aaaaaaaaaa" + "\n\n... (truncated)")


def test_web_fetch_empty_content():
    """コンテンツが空 → エラーメッセージを返す."""
    mock_result = MagicMock()
    mock_result.text_content = "   "
    with patch("markitdown.MarkItDown") as mock_md_cls:
        mock_md_cls.return_value.convert_url.return_value = mock_result
        result = web_fetch.run({"url": "https://example.com"})
    assert "抽出できませんでした" in result


def test_web_fetch_connection_error():
    """ConnectionError → 接続エラーメッセージを返す."""
    import requests

    with patch("markitdown.MarkItDown") as mock_md_cls:
        mock_md_cls.return_value.convert_url.side_effect = requests.ConnectionError()
        result = web_fetch.run({"url": "https://bad.example.com"})
    assert "接続できませんでした" in result


def test_web_fetch_timeout():
    """Timeout → タイムアウトエラーメッセージを返す."""
    import requests

    with patch("markitdown.MarkItDown") as mock_md_cls:
        mock_md_cls.return_value.convert_url.side_effect = requests.Timeout()
        result = web_fetch.run({"url": "https://slow.example.com"})
    assert "タイムアウト" in result


def test_web_fetch_http_error_with_status():
    """HTTPError → 汎用エラーメッセージを返す（除外セキュリティのため）."""
    import requests

    http_err = requests.HTTPError()
    mock_response = MagicMock()
    mock_response.status_code = 404
    http_err.response = mock_response
    with patch("markitdown.MarkItDown") as mock_md_cls:
        mock_md_cls.return_value.convert_url.side_effect = http_err
        result = web_fetch.run({"url": "https://notfound.example.com"})
    # ステータスコードはエラーメッセージに含まれない（セキュリティのため）
    assert "HTTPエラー" in result


def test_web_fetch_unexpected_error():
    """予期しない例外 → 汎用エラーメッセージを返す（例外詳細はログのみ）."""
    with patch("markitdown.MarkItDown") as mock_md_cls:
        mock_md_cls.return_value.convert_url.side_effect = ValueError("parse failed")
        result = web_fetch.run({"url": "https://example.com"})
    assert "予期しないエラー" in result
    # 例外クラス名はエラーメッセージに含まれない（セキュリティのため）
    assert "ValueError" not in result


# ─── get_current_time ─────────────────────────────────────────────────────────


def test_get_current_time_returns_formatted_string():
    """Asia/Tokyo のデフォルトタイムゾーンで現在時刻を返す."""
    import re

    result = get_current_time.run({})
    # "YYYY-MM-DD HH:MM:SS TZ" 形式を検証
    assert re.match(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} ", result)


def test_get_current_time_utc():
    """UTC タイムゾーンでも正しく動作する."""
    result = get_current_time.run({"timezone": "UTC"})
    assert "UTC" in result


def test_get_current_time_unknown_timezone():
    """不明なタイムゾーン → エラーメッセージを返す."""
    result = get_current_time.run({"timezone": "Invalid/Zone"})
    assert "不明なタイムゾーン" in result
    assert "Invalid/Zone" in result
