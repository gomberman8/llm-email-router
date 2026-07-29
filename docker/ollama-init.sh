#!/bin/sh
set -eu

: "${OLLAMA_MODEL:?OLLAMA_MODEL must be set}"

echo "ollama-init: pulling ${OLLAMA_MODEL} from ${OLLAMA_HOST}"
ollama pull "${OLLAMA_MODEL}"
echo "ollama-init: ${OLLAMA_MODEL} ready"
