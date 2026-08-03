#!/bin/sh
set -eu

: "${OLLAMA_MODEL:?OLLAMA_MODEL must be set}"

if ollama list | grep -q "^${OLLAMA_MODEL}[[:space:]]"; then
    echo "ollama-init: ${OLLAMA_MODEL} already in the volume, skipping pull"
    exit 0
fi

echo "ollama-init: pulling ${OLLAMA_MODEL} from ${OLLAMA_HOST}"
ollama pull "${OLLAMA_MODEL}"
echo "ollama-init: ${OLLAMA_MODEL} ready"
