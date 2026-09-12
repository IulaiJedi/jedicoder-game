#!/usr/bin/env bash
# Акт 3, квест 06: context7 подключён — свежие доки вместо устаревшей памяти.
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/emit.sh"

# Три признака: project-scope (.mcp.json), user-scope и plugin-scope
# (claude mcp get). Exit-коды `claude mcp get` проверены вживую 2026-07-27.
# Где нашли — в строке проверки: на машине автора квест закрывался сам по
# глобальному MCP, и падаван не понимал, что именно засчитано (живой прогон
# 2026-09-10). Место ищем до jc_check, чтобы подпись его назвала.
CONTEXT7_WHERE=""
if [ -f .mcp.json ] && grep -c 'context7' .mcp.json >/dev/null 2>&1; then
  CONTEXT7_WHERE="в проекте: .mcp.json"
elif command -v claude >/dev/null 2>&1 \
    && { claude mcp get context7 >/dev/null 2>&1 \
         || claude mcp get plugin:context7:context7 >/dev/null 2>&1; }; then
  CONTEXT7_WHERE="на этой машине, для всех проектов: claude mcp"
fi

has_context7() { [ -n "$CONTEXT7_WHERE" ]; }

LABEL="MCP-сервер context7 подключён"
[ -n "$CONTEXT7_WHERE" ] && LABEL="$LABEL ($CONTEXT7_WHERE)"

jc_init "act3/06-context7"
jc_check context7_connected "$LABEL" \
  "Подключи: claude mcp add --scope project context7 -- npx -y @upstash/context7-mcp" \
  has_context7
jc_finish
