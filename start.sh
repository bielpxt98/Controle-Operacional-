#!/bin/bash
set -e

if [ -d "whatsapp-bot" ] && command -v node >/dev/null 2>&1; then
    echo "Iniciando whatsapp-bot..."
    (cd whatsapp-bot && node index.js) &
fi

PORT="${PORT:-10000}"
echo "Iniciando Gunicorn na porta $PORT..."

exec gunicorn app:app --bind 0.0.0.0:"$PORT" --timeout 300 --workers 1 --threads 4
