---
name: web-research-workflow
description: Use this skill whenever the user wants to research a topic — even if they don't explicitly say "web research". Trigger on "research X and summarize", "find information about X", "調べて", "リサーチして", or any task requiring fact-finding from the internet. HTML Report/article generation is optional and only runs when the user explicitly requests a polished report or article.
---

# Web Research Workflow

## Workflow (3 Required Steps + 2 Optional Steps)

### Step 0: Create Workflow Plan (TodoWrite)

Before doing anything else, use `write_todos` to create a plan for this workflow execution. The todos should reflect which steps will actually run (required steps always included; optional steps only if the user requested a report).

**Example todos:**
```
- [ ] Step 1: Clarify research goal and determine complexity
- [ ] Step 2: Dispatch web_researcher
- [ ] Step 3: Verify research file and check plan status
- [ ] Step 4: Dispatch final_report_creator  ← only if report requested
- [ ] Step 5: Verify HTML output and check plan status  ← only if Step 4 runs
```

---

### Step 1: Clarify the Research Goal

Summarize the user's request into a single, comprehensive research goal. Do **not** decompose into multiple topics — one `web_researcher` call covers the entire goal.

Also determine the **output language** from the user's explicit instruction. Default to **Japanese** if no language is specified.

Also assess the **complexity** of the research goal:
- **Simple**: Factual lookups, well-known topics, single-domain questions
- **Complex**: Multi-faceted topics, rapidly evolving fields, requires synthesizing conflicting sources, deep technical analysis, or broad historical/comparative scope

Record the complexity assessment alongside the goal. It will be passed to `web_researcher` in Step 2.

**Example** — "AIの歴史について記事を書いて":
- Goal: "Key milestones, breakthroughs, and societal impact of AI history from the 1950s to the present"
- Language: Japanese
- Complexity: **Complex** — spans 70+ years, multiple subfields, requires synthesizing diverse sources

Rules:
- Keep the goal broad enough to cover all aspects in one call
- Be specific enough that the researcher knows what to focus on
- If the user explicitly specifies a language, use that; otherwise default to **Japanese**

---

### Step 2: Dispatch web_researcher (Single Call)

Launch **one** `web_researcher` subagent using the `task` tool with `subagent_type="web_researcher"`. Pass the full research goal to a single agent.

If the complexity assessed in Step 1 is **Complex**, explicitly state **"This is a complex problem."** at the top of the description.

**Example dispatch (via Agent tool) — complex goal:**
```
subagent_type: web_researcher
description: |
  This is a complex problem.

  Search the web for "Key milestones, breakthroughs, and societal impact of AI history
  from the 1950s to the present, including the Turing Test, expert systems, deep learning,
  and modern AI applications."
  Collect at least 3 reliable sources.
  Write all findings in Japanese.
  Save findings to a Markdown file and return the file path.
```

**Example dispatch — simple goal:**
```
subagent_type: web_researcher
description: |
  Search the web for "Current capital city of Australia."
  Collect at least 3 reliable sources.
  Write all findings in Japanese.
  Save findings to a Markdown file and return the file path.
```

Always instruct the `web_researcher` to:
1. Collect findings from at least 3 reliable sources
2. Write the findings in the language determined in Step 1
3. Save the findings to a Markdown file
4. Return the file path of the saved file

---

### Step 3: Verify Research File Exists

Verify the file returned by `web_researcher`:

```
read_file(path=<returned_path>, max_lines=5)
```

Check:
- [ ] File exists and is readable
- [ ] File contains non-empty content (not just a title)

If a file is missing or empty → see Error Handling below.

**Plan status check:** After completing verification, review the todo list and mark Step 3 complete. Confirm which remaining todos are still pending before proceeding.

After Step 3, present the research file path to the user and ask if they want a polished report generated. If they do not request one, the workflow is complete.

---

### Step 4 (Optional): Dispatch final_report_creator

**Only run this step if the user explicitly requests a polished report or article.**

Pass the **file path** (not content) from Steps 2–3 to `final_report_creator` using the `task` tool with `subagent_type="final_report_creator"`.

**Example dispatch (via Agent tool):**
```
subagent_type: final_report_creator
description: |
  Read the research draft from:
  - /research_results/20250313_103000_ai_history.md

  Produce a polished HTML report on AI history written in Japanese.
  Save to HTML file and return the file path.
```

Rules:
- Pass file paths, never raw content
- Describe the desired tone, structure, and audience in the goal
- Specify the output language explicitly (use the language determined in Step 1)
- Include `nuance` if the user specified a tone

---

### Step 5 (Optional): Verify HTML Output

**Only run this step if Step 4 was executed.**

```
read_file(path=<html_path>, max_lines=5)
```

Check:
- [ ] File exists and is readable
- [ ] Content starts with `<!DOCTYPE html>`
- [ ] File is not empty

If verification fails → see Error Handling below.

**Plan status check:** After completing verification, review the todo list and mark Step 5 complete. Confirm all todos are now complete before marking the workflow done.

---

## ❌ Anti-patterns (Never Do)

| Anti-pattern | Why it's wrong |
|--------------|----------------|
| Calling `web_search` or `web_fetch` directly | Bypasses the orchestration; breaks parallel execution and error recovery |
| Passing raw content to `final_report_creator` | Agent expects file paths — content will be ignored or cause errors |
| Dispatching multiple `web_researcher` agents | Only one call is needed; splitting topics adds unnecessary complexity |
| Skipping file verification (Step 3) | Passing bad paths to `final_report_creator` causes silent failure |
| Giving vague goals to `web_researcher` | Small models need precise instructions to return useful results |
| Skipping Step 0 (TodoWrite) | No plan means no status tracking; easy to skip steps or lose progress |
| Omitting complexity label for complex goals | `web_researcher` may underallocate effort without the hint |

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

**Always required:**
- [ ] Step 0: TodoWrite plan was created before starting
- [ ] `web_researcher` output has been read and verified (Step 3)
- [ ] Plan status was checked after Step 3
- [ ] User has been given the research file path

**Only if report was requested (Steps 4–5):**
- [ ] `final_report_creator` was given file paths (not raw content)
- [ ] HTML output starts with `<!DOCTYPE html>`
- [ ] HTML file is non-empty and readable
- [ ] Plan status was checked after Step 5
- [ ] User has been given the final HTML file path (or URL if served)
