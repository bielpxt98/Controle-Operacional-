#!/bin/bash
cd whatsapp-bot
node index.js &
cd ..
gunicorn app:app
