---
name: web-research-workflow
description: Use this skill whenever the user wants to research a topic and produce a polished report or article — even if they don't explicitly say "web research" or "HTML". Trigger on: "write an article about X", "research X and summarize", "create a report on X", "find information about X", "compile findings on X", "調べてレポートを書いて", "記事を作って", "リサーチして", or any task requiring fact-finding from the internet followed by a structured written output. This skill orchestrates web_researcher and final_report_creator subagents, handles parallel research queries, and verifies the final HTML output.
---

# Web Research Workflow

## Workflow (5 Steps — Follow in Order)

### Step 1: Decompose the Goal into Research Topics

Break the user's request into 2–5 independent research topics. Each topic should be focused enough for one `web_researcher` call.

**Example decomposition** — "AIの歴史について記事を書いて":
- Topic A: "Key milestones in AI history from 1950s to 2000s"
- Topic B: "Deep learning breakthroughs and modern AI (2010–present)"
- Topic C: "Real-world AI applications and societal impact"

Rules:
- Each topic must be self-contained (no cross-dependencies between topics)
- Keep topics at the same level of abstraction
- Avoid overlapping scope between topics

---

### Step 2: Dispatch web_researcher (Parallel for Independent Topics)

Launch `web_researcher` subagents in **parallel** (up to 3 simultaneously) using the `task` tool with `subagent_type="web_researcher"`. Pass one focused goal per agent.

**Example dispatch (via Agent tool):**
```
subagent_type: web_researcher
description: |
  Search the web for: "Key milestones in AI history from 1950s to 2000s, including
  the Turing Test, expert systems, and early neural networks."
  Collect at least 3 reliable sources.
  Save findings to /research_results/YYYYMMDD_HHMMSS_{slug}.md and return the file path.
```

Always instruct each `web_researcher` to:
1. Collect findings from at least 3 reliable sources
2. Save the findings to a Markdown file
3. Return the file path of the saved file

---

### Step 3: Verify Research Files Exist

Before proceeding to report generation, verify each file returned by `web_researcher`:

```
read_file(path=<returned_path>, max_lines=5)
```

Check:
- [ ] File exists and is readable
- [ ] File contains non-empty content (not just a title)

If a file is missing or empty → see Error Handling below.

---

### Step 4: Dispatch final_report_creator

Pass the **file paths** (not content) from Steps 2–3 to `final_report_creator` using the `task` tool with `subagent_type="final_report_creator"`.

**Example dispatch (via Agent tool):**
```
subagent_type: final_report_creator
description: |
  Read and combine the research drafts from:
  - /research_results/20250313_103000_ai_history_1950s.md
  - /research_results/20250313_103100_ai_deep_learning.md
  - /research_results/20250313_103200_ai_applications.md

  Produce a polished HTML report on AI history. Save to /reports/YYYYMMDD_HHMMSS_{slug}.html
  and return the file path.
```

Rules:
- Pass file paths, never raw content
- Describe the desired tone, structure, and audience in the goal
- Include `nuance` if the user specified a tone

---

### Step 5: Verify HTML Output

```
read_file(path=<html_path>, max_lines=5)
```

Check:
- [ ] File exists and is readable
- [ ] Content starts with `<!DOCTYPE html>`
- [ ] File is not empty

If verification fails → see Error Handling below.

---

## ❌ Anti-patterns (Never Do)

| Anti-pattern | Why it's wrong |
|--------------|----------------|
| Calling `web_search` or `web_fetch` directly | Bypasses the orchestration; breaks parallel execution and error recovery |
| Passing raw content to `final_report_creator` | Agent expects file paths — content will be ignored or cause errors |
| Dispatching a single `web_researcher` for all topics | Serializes work unnecessarily; use parallel calls for independent topics |
| Skipping file verification (Step 3) | Passing bad paths to `final_report_creator` causes silent failure |
| Giving vague goals to `web_researcher` | Small models need precise instructions to return useful results |
| Dispatching more than 3 agents in parallel | Exceeds resource limits; batch similar queries into one agent |

---

## Error Handling

| Failure | Recovery Action |
|---------|----------------|
| `web_researcher` returns no file path | Retry once with a more specific goal (add source type, date range, or concrete examples to request) |
| `web_researcher` returns empty file | Check if goal was too narrow; broaden scope slightly and retry |
| `web_researcher` fails twice | Record the gap in a stub Markdown file (e.g., `"[GAP: topic X not found]"`) and continue with available drafts |
| `final_report_creator` fails | Provide draft file paths to user directly and note the failure; offer Markdown version as fallback |
| HTML file missing after Step 4 | Re-run `final_report_creator` with same file paths; if fails again, output Markdown drafts to user |
| HTML file does not start with `<!DOCTYPE html>` | Re-run `final_report_creator` with explicit instruction: "Output must be a valid HTML5 document starting with `<!DOCTYPE html>`" |

---

## Verification Checklist

Before marking the task complete:

- [ ] All `web_researcher` outputs have been read and verified (Step 3)
- [ ] `final_report_creator` was given file paths (not raw content)
- [ ] HTML output starts with `<!DOCTYPE html>`
- [ ] HTML file is non-empty and readable
- [ ] User has been given the final HTML file path (or URL if served)
