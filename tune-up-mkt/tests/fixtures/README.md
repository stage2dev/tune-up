# Fixtures

Anonymized copies of real command outputs, used by tests that parse them.
Captured 2026-11-12 with Claude Code 2.1.322 and Composio CLI 0.2.32.
Every value (paths, user names, hosts, connection ids, dates) is fictitious:
the structure, key names, punctuation and marks are kept as captured.

Measured durations on the capture machine: `claude mcp list` 21.2 s,
`composio connections list` 5.4 s. Callers must allow for that.

## Files

| File | Scenario |
|---|---|
| `plugin_list_ligado.json` | `claude plugin list --json`: openseo, claude-ads, marketing, tune-up, composio present and enabled |
| `plugin_list_ausente.json` | none of the marketing plugins |
| `plugin_list_desligado.json` | openseo present with `enabled: false` |
| `mcp_list_ligado.txt` | `claude mcp list`: openseo and composio connected |
| `mcp_list_falta_autenticar.txt` | openseo and composio with `! Needs authentication` |
| `mcp_list_ausente.txt` | no openseo and no composio line |
| `mcp_list_estados.txt` | one line per status listed below |
| `mcp_list_formato_desconhecido.txt` | table layout, not a real output (for "unknown format" tests) |
| `composio_connections_ligado.json` | `composio connections list`: metaads ACTIVE + EXPIRED, googleads, instagram, facebook ACTIVE |
| `composio_connections_expirado.json` | metaads only EXPIRED |
| `composio_connections_vazio.json` | `{}` |
| `composio_connections_metaads.json` | `--toolkit metaads` shape |
| `composio_connections_formato_desconhecido.json` | a list instead of an object, not a real output |

The `plugin_list_*` items keep every key shape seen in the capture (the
optional keys `mcpServers`, `readFromFolder`, `folderVersion`, `hasUserConfig`
and the synced entry without dates or `projectEnabled`).

## `claude mcp list` statuses

Source for the doc-only ones: https://code.claude.com/docs/en/mcp (read 2026-11-12).

| Status line | Source |
|---|---|
| `✔ Connected` | observed for real; also in the docs |
| `! Needs authentication` | observed for real; also in the docs |
| `- Not configured` | observed for real (on `plugin:marketing:*` entries with an empty URL); NOT in the docs |
| `✘ Failed to connect` | docs only; the docs say the failure detail is appended to the line |
| `⏸ Pending approval (run `claude` to approve)` | docs only (project-scoped server not yet approved) |
| `⊘ Disabled for this project (re-enable via /mcp)` | docs only |

For the doc-only states the marks above are copied from the docs text, but
they were never seen in a real capture, so treat the exact mark characters as
unconfirmed. Parsers should key on the words, not on the mark.
