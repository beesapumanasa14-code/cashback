#!/bin/sh
set -eu

ollama serve &
ollama_pid=$!
trap 'kill "$ollama_pid" 2>/dev/null || true' EXIT

until curl --fail --silent http://127.0.0.1:11434/api/tags >/dev/null; do
    sleep 2
done

if [ "${OLLAMA_PULL_MODEL:-false}" = "true" ]; then
    ollama pull "${OLLAMA_MODEL:-gemma4:e2b}"
fi

streamlit run main.py --server.address 0.0.0.0 --server.port "${PORT:-7860}" --server.headless true &
app_pid=$!
trap 'kill "$app_pid" "$ollama_pid" 2>/dev/null || true' EXIT INT TERM
wait "$app_pid"
