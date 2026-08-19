#!/bin/bash
cd whatsapp-bot
npm install
node index.js &
cd ..
gunicorn app:app
