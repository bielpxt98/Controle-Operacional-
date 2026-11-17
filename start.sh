#!/bin/bash
set -e

if [ -d "whatsapp-bot" ] && command -v node >/dev/null 2>&1; then
    echo "Iniciando whatsapp-bot com auto-recuperacao..."
    (
        cd whatsapp-bot
        while true; do
            echo "[$(date)] Iniciando processo do whatsapp-bot..." >> /app/bot.log
            node index.js >> /app/bot.log 2>&1
            EXIT_CODE=$?
            echo "[$(date)] whatsapp-bot encerrou (codigo $EXIT_CODE). Reiniciando em 3s..." >> /app/bot.log
            sleep 3
        done
    ) &
fi

PORT="${PORT:-10000}"
echo "Iniciando Gunicorn na porta $PORT..."

exec gunicorn app:app --bind 0.0.0.0:"$PORT" --timeout 300 --workers 1 --threads 4
