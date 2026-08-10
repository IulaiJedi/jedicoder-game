#!/usr/bin/env bash
# Акт 3, квест 06: context7 подключён — свежие доки вместо устаревшей памяти.
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/emit.sh"

# Три признака: project-scope (.mcp.json), user-scope и plugin-scope
# (claude mcp get). Exit-коды `claude mcp get` проверены вживую 2026-07-27.
has_context7() {
  if [ -f .mcp.json ] && grep -c 'context7' .mcp.json >/dev/null 2>&1; then
    return 0
  fi
  if command -v claude >/dev/null 2>&1; then
    claude mcp get context7 >/dev/null 2>&1 && return 0
    claude mcp get plugin:context7:context7 >/dev/null 2>&1 && return 0
  fi
  return 1
}

jc_init "act3/06-context7"
jc_check context7_connected "MCP-сервер context7 подключён" \
  "Подключи: claude mcp add --scope project context7 -- npx -y @upstash/context7-mcp" \
  has_context7
jc_finish
