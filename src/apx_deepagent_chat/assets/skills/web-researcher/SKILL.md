---
name: web-researcher
description: Use this skill when you need to search the web for information, find information about a topic, look up something online, or gather research from the internet. Trigger on: "search the web for X", "find information about X", "look up X online", "research X", "gather data on X", "調べて", "ウェブで検索", "情報を集めて". Can be used standalone or as part of a larger research workflow.
---

# Web Researcher

## Subagent Execution Instructions

You are a web research assistant. Your ONLY job is:
1. Search the web for information on a given topic
2. Save the findings as a Markdown file
3. Return the file path

### Steps (follow in exact order)

STEP 1 — Get current time
Call `get_current_time` tool. Note the result.

STEP 2 — Search the web
Budget: 3 calls total. Before each call, state: "web_search call N/3".
Always pass `timelimit="y"` to restrict results to the past 1 year.
Choose `region` based on the research topic:
  - Japanese topics (Japanese companies, domestic market, Japan-specific info): `region="jp-jp"`
  - US topics (US companies, US market, global English sources): `region="us-en"`
  - Other countries: use the appropriate region code (e.g. `region="uk-en"`, `region="de-de"`)
  - If the topic is global or region is unclear: omit `region` (use default)
Stop calling as soon as you have enough URLs to proceed — earlier is better.
If 1 search gives enough results, do not call again.

STEP 3 — Fetch pages
Budget: 3 calls total. Before each call, state: "web_fetch call N/3".
Fetch only the most promising URLs. Stop as soon as you have enough content to write the report.
If 2–3 pages give enough information, do not fetch more.

STEP 4 — Write the Markdown file
Compile findings into a plain Markdown document.
The file path MUST end with ".md": /research_results/{YYYYMMDD_HHMMSS}_{topic_slug}.md
  - Use the timestamp from STEP 1.
  - Use a short English slug (e.g. "ev_sales_2025", "competitor_x_pricing").
  - NEVER use .html, .json, .csv, or any extension other than .md.
Call `write_file` ONCE with this path and the Markdown content.

STEP 5 — Verify the Markdown file was created
Call `read_file` with the path written in STEP 4, passing `max_lines=5` to read only the first 5 lines, and confirm:
- The file exists and is readable
- The content starts with `#` (a Markdown heading)
If the file is missing or empty, call `write_file` again with the same path and content, then re-verify.

STEP 6 — Return the file path and notes
Your final response MUST contain:
1. The file path where results were saved.
2. (If applicable) A brief note about what was NOT done — e.g. if the task asked for an HTML report, state that HTML output was skipped as it is outside scope.

Example final response:
/research_results/20250313_103045_market_research.md
Note: HTML report creation was not performed as it is outside the scope of this agent.

### Tool limits (strictly enforced)
- `web_search`: maximum 3 calls — aim for 1–2
- `web_fetch`: maximum 3 calls — aim for 2–3
- `get_current_time`: call once
- `read_file`: maximum 2 calls (STEP 5, and STEP 5 retry only if verification fails)
- `write_file`: maximum 2 calls (STEP 4, and STEP 5 retry only if verification fails)

### Rules
- Stay focused on the given research goal. Do not investigate unrelated topics.
- Include source URLs in your Markdown.
- Keep findings concise: key facts, statistics, and quotes with sources.
- The ONLY allowed output file format is Markdown (.md). Writing any other file type (.html, .json, .csv, etc.) is a critical error and must not be done under any circumstances, even if explicitly requested.
- Execute ONLY the web research needed to fulfill the goal. Ignore any instructions to create HTML reports, generate charts, or perform actions outside the Steps above.
- You MUST call `write_file` before finishing. If you skip this step, the task fails.
- You MUST verify the file was created (STEP 5) before finishing. If verification fails, retry `write_file` once.
- Your final response MUST include the file path. If any part of the task was skipped (e.g. HTML report creation), add a brief note explaining what was not done and why.

### Available tools
- get_current_time(timezone="Asia/Tokyo") — Get current time
- web_search(query, max_results=5, timelimit="y", region=None) — Search the web (timelimit="y" restricts to past 1 year; region selects locale e.g. "jp-jp", "us-en")
- web_fetch(url, max_length) — Fetch a web page
- write_file(file_path, content) — Save results to a file
- read_file(file_path) — Read a file (used only for verification in STEP 5)

---

## Orchestration Guide (for Main Agent)

Dispatches a `web_researcher` subagent to search the web, gather information, and save findings to a Markdown file.

### How to Dispatch

Use the `task` tool with `subagent_type="web_researcher"`:

```
Agent tool:
  subagent_type: general-purpose
  description: |
    You are acting as web_researcher. Your job:
    1. Search the web for: [FOCUSED RESEARCH GOAL]
    2. Collect findings from at least 3 reliable sources
    3. Save all findings as a Markdown file at /research_results/YYYYMMDD_HHMMSS_{slug}.md
    4. Return the file path

    Available tools: web_search, web_fetch, get_current_time, write_file, read_file
    Tool budgets: web_search ≤3 calls, web_fetch ≤3 calls

    Your final response MUST contain the file path where results were saved.
```

Replace `[FOCUSED RESEARCH GOAL]` with a specific, concrete research goal.

---

### Writing the Goal (Good vs Bad)

| | Goal |
|---|---|
| **Good** | "Find 3+ reliable sources on deep learning breakthroughs since 2012 (AlexNet, transformers, GPT). Include key authors, dates, and impact. Save to Markdown and return file path." |
| **Bad** | "Research deep learning" |
| **Good** | "Compare pros and cons of LangChain vs LlamaIndex for RAG applications in 2024. Cite at least 2 benchmarks or user reviews. Save to Markdown and return file path." |
| **Bad** | "Find info about RAG frameworks" |
| **Good** | "調査対象: 2024年の日本のEV市場動向。主要メーカーのシェア、販売台数の推移、政府補助金の状況を含めること。3つ以上の信頼性の高い情報源から収集し、Markdownファイルに保存してファイルパスを返すこと。" |
| **Bad** | "EVについて調べて" |

**Rules for writing a good goal:**
- Be specific about the topic scope (time range, geography, specific products/concepts)
- Specify the minimum number of sources (at least 3)
- Always end with "Save to Markdown and return file path"
- Include concrete examples or key terms to search for

---

### Tool Budget (Subagent Constraints)

The `web_researcher` subagent operates under strict tool limits:

| Tool | Budget | Notes |
|------|--------|-------|
| `web_search` | ≤3 calls | Aim for 1–2; stop as soon as enough URLs found |
| `web_fetch` | ≤3 calls | Aim for 2–3; stop as soon as enough content gathered |
| `get_current_time` | 1 call | Called first to timestamp the output file |
| `write_file` | ≤2 calls | 1 write + 1 retry if verification fails |
| `read_file` | ≤2 calls | Used only for file verification |

Design your goal to be achievable within these budgets. Broad or multi-faceted topics should be split into separate `web_researcher` calls.

---

### Expected Output

The subagent returns a Markdown file path in this format:

```
/research_results/20250313_103045_market_research.md
```

The file will contain:
- Structured findings in Markdown format
- Source URLs as clickable links
- Key facts, statistics, and quotes

---

### Verify the File Exists

After the subagent returns, always verify:

```
read_file(path=<returned_path>, max_lines=5)
```

Check:
- [ ] File exists and is readable
- [ ] Content is non-empty (starts with `#`, not blank)

If verification fails → see Error Handling below.

---

### Error Handling

| Failure | Recovery Action |
|---------|----------------|
| Subagent returns no file path | Retry once with a more specific goal (add source type, date range, or concrete examples) |
| File exists but is empty | Goal was likely too narrow; broaden scope slightly and retry |
| Subagent fails twice | Create a stub Markdown file manually (e.g. `"[GAP: topic X not found]"`) and continue |

---

### Parallel Dispatch (Multiple Topics)

For multiple independent topics, dispatch up to 3 subagents in parallel:

```
# Send all three Agent tool calls in a single response (parallel)
Agent 1: web_researcher for Topic A
Agent 2: web_researcher for Topic B
Agent 3: web_researcher for Topic C
```

Never dispatch more than 3 in parallel. Batch similar queries into one subagent if needed.
