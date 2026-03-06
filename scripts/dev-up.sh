#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from .env.example"
fi

get_env() {
  local key="$1"
  local default_val="$2"
  local val
  val="$(grep -E "^${key}=" .env | tail -n1 | cut -d'=' -f2- || true)"
  if [[ -z "$val" ]]; then
    echo "$default_val"
  else
    echo "$val"
  fi
}

set_env() {
  local key="$1"
  local value="$2"
  awk -v k="$key" -v v="$value" '
    BEGIN { found = 0 }
    $0 ~ "^" k "=" { print k "=" v; found = 1; next }
    { print }
    END { if (!found) print k "=" v }
  ' .env > .env.tmp
  mv .env.tmp .env
}

port_in_use() {
  local port="$1"
  lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
}

port_used_by_this_project() {
  local port="$1"
  docker compose ps 2>/dev/null | grep -q ":${port}->"
}

find_free_port() {
  local start="$1"
  local p="$start"
  local max_tries=400
  local i=0
  while (( i < max_tries )); do
    if ! port_in_use "$p"; then
      echo "$p"
      return 0
    fi
    p=$((p + 1))
    i=$((i + 1))
  done

  echo "Could not find a free port starting at ${start}" >&2
  return 1
}

resolve_port() {
  local key="$1"
  local default_port="$2"
  local current
  current="$(get_env "$key" "$default_port")"

  if ! [[ "$current" =~ ^[0-9]+$ ]]; then
    current="$default_port"
  fi

  if port_in_use "$current" && ! port_used_by_this_project "$current"; then
    local new_port
    new_port="$(find_free_port "$current")"
    set_env "$key" "$new_port"
    echo "${key}: ${current} is busy; switched to ${new_port}"
  else
    set_env "$key" "$current"
    echo "${key}: using ${current}"
  fi
}

resolve_port "CORE_SVC_PORT" "8000"
resolve_port "MCP_PORT" "3001"
resolve_port "WEB_PORT" "3000"
resolve_port "EMAIL_MCP_PORT" "3010"
resolve_port "OLLAMA_PORT" "11434"
resolve_port "POSTGRES_PORT" "5432"
resolve_port "REDIS_PORT" "6379"
resolve_port "QDRANT_PORT" "6333"

CORE_SVC_PORT="$(get_env "CORE_SVC_PORT" "8000")"
set_env "CORE_PUBLIC_BASE_URL" "http://localhost:${CORE_SVC_PORT}"

docker compose up -d --build

MCP_PORT="$(get_env "MCP_PORT" "3001")"
WEB_PORT="$(get_env "WEB_PORT" "3000")"
EMAIL_MCP_PORT="$(get_env "EMAIL_MCP_PORT" "3010")"
OLLAMA_PORT="$(get_env "OLLAMA_PORT" "11434")"
QDRANT_PORT="$(get_env "QDRANT_PORT" "6333")"

echo ""
echo "Stack is up:"
echo "- Core API:   http://localhost:${CORE_SVC_PORT}/docs"
echo "- MCP Health: http://localhost:${MCP_PORT}/health"
echo "- Web UI:     http://localhost:${WEB_PORT}"
echo "- Email MCP:  http://localhost:${EMAIL_MCP_PORT}/health"
echo "- Qdrant:     http://localhost:${QDRANT_PORT}/dashboard"
echo "- Ollama API: http://localhost:${OLLAMA_PORT}"
