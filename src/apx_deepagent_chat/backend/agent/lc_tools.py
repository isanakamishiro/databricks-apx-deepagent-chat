from typing import Optional

from langchain_core.tools import tool as langchain_tool


@langchain_tool
def web_search(
    query: str,
    max_results: int = 5,
    region: str = "jp-jp",
    timelimit: Optional[str] = None,
) -> str:
    """DuckDuckGoでWeb検索を行い、結果を返します。最新情報や不明な事実を調べる場合に使用してください。

    Args:
        query: 検索クエリ。
        max_results: 返す検索結果の最大件数。デフォルトは5。
        region: 検索対象の地域コード。デフォルトは"jp-jp"(日本)。例: "us-en", "uk-en", "de-de"。
        timelimit: 検索結果の期間フィルタ。"d"(1日以内), "w"(1週間以内), "m"(1ヶ月以内), "y"(1年以内)。デフォルトはNone(制限なし)。
    """
    from ddgs import DDGS

    try:
        results = list(
            DDGS().text(
                query, region=region, max_results=max_results, timelimit=timelimit
            )
        )
    except TimeoutError:
        return (
            "検索エラー: リクエストがタイムアウトしました。後でもう一度試してください。"
        )
    except Exception as e:
        return f"検索エラー: 予期しないエラーが発生しました: {type(e).__name__}: {e}"

    if not results:
        return "検索結果が見つかりませんでした。"

    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"### {i}. {r.get('title', '(タイトルなし)')}")
        lines.append(f"URL: {r.get('href', '(URLなし)')}")
        lines.append(f"{r.get('body', '')}\n")
    return "\n".join(lines)


@langchain_tool
def web_fetch(url: str, max_length: int = 50000) -> str:
    """URLのWebページを取得し、Markdown形式に変換して返します。Webページの内容を読み取りたい場合に使用してください。

    Args:
        url: 取得するWebページのURL。
        max_length: 返すテキストの最大文字数。デフォルトは50000。
    """
    import requests
    from markitdown import MarkItDown

    try:
        md = MarkItDown()
        result = md.convert_url(url)
    except requests.ConnectionError:
        return f"取得エラー: URL '{url}' に接続できませんでした。URLが正しいか確認してください。"
    except requests.Timeout:
        return f"取得エラー: URL '{url}' への接続がタイムアウトしました。"
    except requests.HTTPError as e:
        return f"取得エラー: HTTPエラーが発生しました (ステータス {e.response.status_code if e.response else '不明'}): {e}"
    except Exception as e:
        return f"取得エラー: 予期しないエラーが発生しました: {type(e).__name__}: {e}"

    text = result.text_content
    if not text or not text.strip():
        return f"取得エラー: URL '{url}' からコンテンツを抽出できませんでした。"
    if len(text) > max_length:
        text = text[:max_length] + "\n\n... (truncated)"
    return text


@langchain_tool
def get_current_time(timezone: str = "Asia/Tokyo") -> str:
    """現在の日時を返します。日時の確認が必要な場合に使用してください。

    Args:
        timezone: タイムゾーン名。デフォルトは"Asia/Tokyo"。例: "UTC", "US/Eastern", "Europe/London"。
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo

    try:
        tz = ZoneInfo(timezone)
    except KeyError:
        return f"エラー: 不明なタイムゾーン '{timezone}'"
    now = datetime.now(tz)
    return now.strftime("%Y-%m-%d %H:%M:%S %Z")
