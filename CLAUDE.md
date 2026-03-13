# apx Project

Full-stack Databricks App built with apx (React + Vite frontend, FastAPI backend).

## Do's and Don'ts
- OpenAPI client auto-regenerates on code changes when dev servers are running - don't manually regenerate.
- Prefer running apx related commands via MCP server if it's available.
- Use the apx MCP `search_registry_components` and `add_component` tools to find and add shadcn/ui components.
- When using the API calls on the frontend, use error boundaries to handle errors.
- Run `apx dev check` command (via CLI or MCP) to check for errors in the project code after making changes.
- If agent has access to native browser tool, use it to verify changes on the frontend. If such tool is not present or is not working, use playwright MCP to automate browser actions (e.g. screenshots, clicks, etc.).
- Avoid unnecessary restarts of the development servers
- **Databricks SDK:** Use the apx MCP `docs` tool to search Databricks SDK documentation instead of guessing or hallucinating API signatures.

## Package Management
- **Frontend:** Use `apx bun install` or `apx bun add <dependency>` for frontend package management.
- **Python:** Always use `uv` (never `pip`)

## Component Management
- **Check configured registries first:** Before building custom components, check `[tool.apx.ui.registries]` in `pyproject.toml` for domain-specific registries (e.g. `@ai-elements` for chat/AI, `@animate-ui` for animations). Use `list_registry_components` with the registry name to browse available components.
- **Finding components:** Use MCP `search_registry_components` to search across all configured registries. Results from project-configured registries are boosted.
- **Adding components:** Use MCP `add_component` or CLI `apx components add <component> --yes` to add components
- **Component location:** If component was added to a wrong location (e.g. stored into `src/components` instead of `src/apx-deepagent-chat/ui/components`), move it to the proper folder
- **Component organization:** Prefer grouping components by functionality rather than by file type (e.g. `src/apx-deepagent-chat/ui/components/chat/`)

## Project Structure
Full-stack app: `src/apx-deepagent-chat/ui/` (React + Vite) and `src/apx-deepagent-chat/backend/` (FastAPI). Backend serves frontend at `/` and API at `/api`. API client auto-generated from OpenAPI schema.

## Dependencies & Dependency Injection

The `Dependency` class in `src/apx-deepagent-chat/backend/core.py` provides typed FastAPI dependencies. **Always use these instead of manually creating clients or accessing `request.app.state`.**

| Dependency | Type | Description |
|---|---|---|
| `Dependencies.Client` | `WorkspaceClient` | Databricks client using app-level service principal credentials |
| `Dependencies.UserClient` | `WorkspaceClient` | Databricks client authenticated on behalf of the current user (requires OBO token) |
| `Dependencies.Config` | `AppConfig` | Application configuration loaded from environment variables |
| `Dependencies.Session` | `Session` | SQLModel database session, scoped to request (requires lakebase addon) |

## Models & API
- **3-model pattern:** `Entity` (DB), `EntityIn` (input), `EntityOut` (output)
- **API routes must have:** `response_model` and `operation_id` for client generation

## Frontend Rules
- **Routing:** `@tanstack/react-router` (routes in `src/apx-deepagent-chat/ui/routes/`)
- **Data fetching:** Always use `useXSuspense` hooks with `Suspense` and `Skeleton` components
- **Pattern:** Render static elements immediately, fetch API data with suspense
- **Components:** Use shadcn/ui, add to `src/apx-deepagent-chat/ui/components/`
- **Data access:** Use `selector()` function for clean destructuring (e.g., `const {data: profile} = useProfileSuspense(selector())`)

## MCP Tools Reference

This project is configured with the **apx MCP server** (see `.mcp.json`). Always prefer MCP tools over CLI commands — they are faster and provide structured output.

| Tool | Description |
|------|-------------|
| `start` | Start development server and return the URL |
| `stop` | Stop the development server |
| `restart` | Restart the development server (preserves port if possible) |
| `logs` | Fetch recent dev server logs |
| `check` | Check project code for errors (runs tsc and ty checks in parallel) |
| `refresh_openapi` | Regenerate OpenAPI schema and API client |
| `search_registry_components` | Search shadcn registry components using semantic search |
| `list_registry_components` | List all available components in a specific registry |
| `add_component` | Add a component to the project |
| `routes` | List all API routes with parameters, schemas, and generated hook names |
| `docs` | Search Databricks SDK documentation for code examples and API references |
| `databricks_apps_logs` | Fetch logs from deployed Databricks app using Databricks CLI |
| `get_route_info` | Get code example for using a specific API route |
| `feedback_prepare` | Prepare a feedback issue for review. Returns formatted title, body, and browser URL |
| `feedback_submit` | Submit a prepared feedback issue as a public GitHub issue |

## Development Commands

CLI equivalents (use MCP tools above when available):

| Command | Description |
|---------|-------------|
| `apx dev start` | Start all dev servers (backend + frontend + OpenAPI watcher) |
| `apx dev stop` | Stop all dev servers |
| `apx dev status` | Check running server status and ports |
| `apx dev check` | Check for TypeScript/Python errors |
| `apx dev logs` | View recent logs (default: last 10m) |
| `apx dev logs -f` | Follow/stream logs live |
| `apx build` | Build for production |

## Detailed Patterns

For backend patterns (DI, CRUD routers, AppConfig, lifespan) and frontend patterns (Suspense, mutations, selector, components), see `.claude/skills/apx/`.

## Workflow Design

### 1. Plan Mode as Default
- Always start with Plan Mode for tasks with 3+ steps or architectural impact.
- If things go wrong mid-way, stop immediately and re-plan rather than pushing through.
- Use Plan Mode not just for building, but also for verification steps.
- Write detailed specs before implementation to reduce ambiguity.

### 2. Subagent Strategy
- Actively use subagents to keep the main context window clean.
- Delegate research, investigation, and parallel analysis to subagents.
- For complex problems, throw more compute at them via subagents.
- Assign one task per subagent for focused execution.

### 3. Self-Improvement Loop
- After receiving corrections from the user, always record the pattern in `tasks/lessons.md`.
- Write rules for yourself to avoid repeating the same mistakes.
- Continuously refine the rules until the error rate drops.
- At the start of each session, review lessons relevant to the project.

### 4. Always Verify Before Marking Complete
- Do not mark a task complete until you can prove it works.
- Check the diff against the main branch when needed.
- Ask yourself: "Would a staff engineer approve this?"
- Run tests, check logs, and demonstrate correct behavior.

### 5. Pursue Elegance (with Balance)
- Before making significant changes, pause and ask: "Is there a more elegant way?"
- If a fix feels hacky, implement an elegant solution using everything you know.
- Skip this process for simple, obvious fixes (avoid over-engineering).
- Self-critique your work before presenting it.

### 6. Autonomous Bug Fixing
- When given a bug report, fix it autonomously without needing hand-holding.
- Look at logs, errors, and failing tests to solve problems yourself.
- Minimize context switching for the user.
- Proactively fix failing CI tests without being asked.

---

## Task Management

1. **Plan first**: Write the plan in `tasks/todo.md` as checkable items.
2. **Review the plan**: Confirm before starting implementation.
3. **Track progress**: Mark completed items as you go.
4. **Explain changes**: Provide a high-level summary at each step.
5. **Document results**: Add a review section to `tasks/todo.md`.
6. **Record learnings**: Update `tasks/lessons.md` after receiving corrections.

---

## Core Principles

- **Simplicity first**: Make every change as simple as possible. Minimize the code affected.
- **No shortcuts**: Find the root cause. Avoid temporary fixes. Maintain senior engineer standards.
- **Minimize impact**: Limit changes to only what is necessary. Don't introduce new bugs.
- When using a browser, use playwright-cli. Save snapshots taken during testing to /screenshots.
- Do not use regular playwright. Always use playwright-cli.