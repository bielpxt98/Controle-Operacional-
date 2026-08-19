#!/bin/bash
cd whatsapp-bot
node --experimental-websocket index.js &
cd ..
gunicorn app:app --bind 0.0.0.0:$PORT
