# AGENTS.md

## Codebase Memory MCP

This repository uses `codebase-memory-mcp` to maintain a local knowledge graph of
the codebase. Use graph tools before broad file reads to save tokens.

Current indexed project name:

`home-vyaspc-Documents-Repo-verity-policy-coverage-eval-framework`

If the project is not indexed, run:

`index_repository(repo_path="/home/vyaspc/Documents/Repo/verity-policy-coverage-eval-framework", mode="fast", persistence=false)`

Use `mode="fast"` for quick orientation. Use `mode="moderate"` or `mode="full"`
only when semantic/similarity results are needed. Use `persistence=true` only
when intentionally writing a shareable `.codebase-memory/graph.db.zst` artifact.

## Token-Saving Discovery Workflow

Prefer this order for code discovery:

1. `list_projects` to confirm the repository is indexed.
2. `get_architecture` for a high-level map of packages, entry points, and hotspots.
3. `search_graph` to find functions, classes, routes, variables, or natural-language concepts.
4. `trace_path` to inspect callers/callees when available in the MCP server.
5. `get_code_snippet` to read exact symbols after `search_graph` returns a qualified name.
6. `query_graph` for complex graph questions when available.
7. Fall back to `rg`/file reads only for string literals, config files, docs, generated files,
   or when graph results are insufficient.

## Practical Query Patterns

- Find a symbol by natural language: `search_graph(query="provider completion")`
- Find by name regex: `search_graph(name_pattern=".*Provider.*")`
- Limit noisy results with `label`, `file_pattern`, `min_degree`, and `exclude_entry_points`.
- Check `has_more`; if true, page with `offset` and `limit` instead of broadening reads.
- Read source only after finding the exact `qualified_name`:
  `get_code_snippet(qualified_name="...")`

## Local Artifact Policy

Do not commit local codebase-memory artifacts by default. The following paths are
ignored intentionally:

- `.codebase-memory/`
- `codebase-memory/`

Only create a persistent artifact when a human explicitly wants a shared graph
snapshot for faster teammate/agent bootstrap.
