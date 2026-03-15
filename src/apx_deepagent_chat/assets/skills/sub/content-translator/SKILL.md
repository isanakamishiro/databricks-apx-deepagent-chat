---
name: content-translator
description: Use this skill when the user wants to translate a web article or URL into another language and save it as a Qiita-formatted Markdown article. Trigger on "translate this URL", "このURLを翻訳してQiita記事にして", "URLの内容を日本語/英語に翻訳して", "記事を翻訳してQiitaに保存して", "translate and save as Qiita article", or any request combining a URL with a translation action. Default target language is Japanese.
---

# URL Translator

Fetches and translates the content of a specified URL, then saves it as a Qiita-formatted Markdown file with a translation credit.
Translate as much as possible, including section names.

## Workflow (4 Steps)

### Step 1: Confirm Input

Confirm the following from the user's request:
- **URL**: The URL to translate (required; ask if not provided)
- **Target language**: Default to **Japanese** if not specified

---

### Step 2: Fetch URL Content

Fetch the URL directly with `web_fetch`:
```
web_fetch(url="{URL}", max_length=50000)
```

If unable to fetch (error message returned) → See Error Handling.

---

### Step 3: Create the Article

**Translate the content fetched in Step 2 into the target language and assemble the article with the following structure.**

#### Disclaimer (must be added at the beginning of the article)

```
:::note info
{NOTE_TEXT}

{source URL}
:::
```

`{NOTE_TEXT}` by target language:

| Target Language | NOTE_TEXT |
|----------------|-----------|
| Japanese | `本記事は以下の内容を翻訳したものです。` |
| English | `This article is a translation of the following content.` |
| Chinese (Simplified) | `本文是使用LLM对以下内容进行翻译的文章。` |
| Korean | `이 글은 LLM 을(를) 사용하여 다음 내용을 번역한 것입니다。` |
| Other | Write the equivalent of "This article is a translation of the following content." in the target language |

#### Translation Rules

- Translate the entire body into the target language
- Preserve Markdown structure (headings, lists, code blocks, bold, links, etc.)
- **Do not translate** code inside code blocks (comments may be translated)
- Do not translate URLs or proper nouns (product names, company names, person names)
- If the source content is already in the target language, skip translation (notify the user and use the original text as-is)

---

### Step 4: Save and Verify the File

Get the current time to use in the file name:
```
get_current_time(timezone="Asia/Tokyo")
```

Generate a slug (short English identifier) from the URL and save:
```
write_file(
  file_path=/qiita_articles/{YYYYMMDD_HHMMSS}_{slug}.md,
  content=<full article created in Step 3>
)
```

**Call `write_file` exactly once. Do not call it again regardless of what happens next.**

```
write_file(
  file_path=/qiita_articles/{YYYYMMDD_HHMMSS}_{slug}.md,
  content=<full article created in Step 3>
)
```

- If `write_file` itself returns an error → retry exactly once, then stop
- If `write_file` succeeds (no error returned) → do NOT call `write_file` again under any circumstances

Verify the file exists by reading it:
```
read_file(path=<above path>, max_lines=5)
```

If `read_file` fails or the file appears unreadable → output the article content directly in the chat (do NOT call `write_file` again).

Return to the user:
1. The saved file path
2. A summary of the translation (e.g., "English → Japanese", one-line description of the article topic)

---

## Anti-Patterns (What NOT to Do)

| Anti-Pattern | Reason |
|-------------|--------|
| Dispatching a `web_researcher` subagent to fetch the URL | The main agent has direct access to `web_fetch` — no subagent needed |
| Always writing the disclaimer in Japanese | The disclaimer must be written in the target language |
| Translating code inside code blocks | Code is language-dependent and must not be translated |
| Summarizing or paraphrasing | This must be a full translation. Do not omit important information |
| Skipping the file verification | Always perform the Step 4 verification |
| Calling `write_file` more than once | `write_file` must be called exactly once. Only retry if `write_file` itself returns an error. Verification failure is NOT a reason to call `write_file` again |

---

## Error Handling

| Situation | Action |
|-----------|--------|
| `web_fetch` returns an error | Verify the URL and notify the user. Inform them the page may require authentication or the URL may not exist |
| Content is too large and was truncated ("truncated" appears at the end) | Proceed with translation and add a note to the article: "※ Some content may be missing" |
| `write_file` fails | Retry once. If it still fails, output the article content directly in the chat |
| Source content is already in the target language | Skip translation, add only the disclaimer, and save (notify the user) |
