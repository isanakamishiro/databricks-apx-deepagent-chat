---
name: content-writing-workflow
description: Use this skill for content writing tasks — either translating a URL into a Qiita-formatted article, or writing a new Qiita article from scratch. Trigger on "記事を書いて", "URLを翻訳してQiita記事にして", "write a Qiita article", "translate this URL", "ブログ記事を作って", "技術記事を書いて", or any request to create written content for Qiita/blog. Routes to content-translator (URL translation) or article-writer (original article) sub-skills.
---

# Content Writing Workflow

A workflow that analyzes content creation tasks and routes them to the appropriate sub-skill.

## Workflow (4 Steps)

### Step 1: Request Analysis and Declaration

Classify the user's request using the following criteria:

| Condition | Sub-skill to Use |
|-----------|-----------------|
| Contains a URL with intent to "translate", "日本語で", "英語で", etc. | `content-translator` |
| Contains a markdown file path with intent to write an article or blog post | `article-writer` |

Declare the chosen sub-skill to the user. Examples:
- "I will translate the URL and save it as a Qiita article. Using the `content-translator` skill."
- "I will write a Qiita article. Using the `article-writer` skill."

---

### Step 2: Dispatch the content_writer Subagent

> **RULE: Subagent must be dispatched exactly once per task.**
> Dispatching multiple subagents (in parallel or sequentially) is strictly prohibited unless an error occurs and a retry is required per the Error Handling section. Even if the first result seems incomplete, do NOT dispatch a second subagent — report the issue to the user instead.

Dispatch **exactly one** `content_writer` subagent using the Agent tool.

#### Dispatch example for content-translator:

```
subagent_type: content_writer
description: |
  Follow the `content-translator` skill workflow below to translate the URL content and save it as a Qiita article.

  [Task Information]
  - Target URL: {URL}
  - Target language: {target language (default: Japanese)}

  [content-translator Skill Workflow]
  Step 1: Confirm input (URL, target language, your own model name)
  Step 2: Fetch URL content with web_fetch
  Step 3: Create the Qiita article
    - Add a translation credit :::note info block at the top
    - Translate the entire body to the target language (do NOT translate code inside code blocks)
    - Preserve the Markdown structure
  Step 4: Save to /qiita_articles/{YYYYMMDD_HHMMSS}_{slug}.md and confirm

  Return the saved file path when done.
```

#### Dispatch example for article-writer:

```
subagent_type: content_writer
description: |
  Follow the `article-writer` skill workflow below to create a Qiita article.

  [Task Information]
  - Source Markdown File Path: {path to the user's draft/notes/outline file}
  - Content Overview: {brief description of the file's content}

  [article-writer Skill Workflow]
  Step 1: Read the specified markdown file
    - Read the file at the given path and use its content as the source material
    - If the path is missing or the file cannot be read, return an error to the caller
  Step 2: Write the article
    - Strictly follow writing style and language rules ("個人的には", "とはいえ", "〜してみました", etc.)
    - Follow Qiita conventions: :::note syntax, bare URL pasting, four-point summary
    - Save to /qiita_articles/{YYYYMMDD_HHMMSS}_{slug}.md

  Return the saved file path when done.
```

**Important constraints:**
- Do NOT dispatch both `content-translator` and `article-writer` at the same time
- Do NOT dispatch multiple subagents in parallel
- Do NOT dispatch a second subagent after the first completes — one dispatch per task is the rule
- The only exception is an error retry as defined in the Error Handling section

---

### Step 3: Verify the Output File

Check the file path returned by the subagent:

```
read_file(path=<returned path>, max_lines=5)
```

Verification checklist:
- [ ] A file path was returned
- [ ] The file exists and is readable
- [ ] The file is not empty

If any check fails → see Error Handling.

---

### Step 4: Completion Report

Tell the user:
1. The saved file path
2. A brief summary of the content (1–2 lines)

Example: "Saved to `/qiita_articles/20260315_120000_langchain-rag.md`. This is a Japanese translation of an overview and implementation guide for LangChain RAG."

---

## ❌ Anti-patterns

| Anti-pattern | Reason |
|-------------|--------|
| Calling `web_fetch` directly | Delegate to the subagent |
| Calling `write_file` directly | Delegate to the subagent |
| Dispatching both `content-translator` and `article-writer` | Use only one |
| Dispatching a second subagent after the first | One dispatch per task — prohibited unless error retry |
| Dispatching multiple subagents in parallel | Strictly prohibited regardless of reason |
| Skipping file verification (Step 3) | Required for early detection of invalid paths |
| Executing directly without a subagent | This workflow is designed to delegate to a subagent |

---

## Error Handling

| Situation | Action |
|-----------|--------|
| No file path returned | Retry once with the same sub-skill |
| No file path after retry | Report the error to the user and ask for manual confirmation |
| File is empty or unreadable | Retry once with the same sub-skill |
| Two consecutive failures | Report the error to the user |

---

## Validation Checklist

Before marking the task complete:
- [ ] Request analysis was accurate and the correct sub-skill was selected
- [ ] Exactly one subagent was dispatched
- [ ] File path was confirmed and the file exists and is non-empty
- [ ] File path and content summary were reported to the user
