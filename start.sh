#!/bin/bash
cd whatsapp-bot
node index.js &
cd ..
gunicorn app:app --bind 0.0.0.0:$PORT --timeout 300 --workers 1 --threads 4
