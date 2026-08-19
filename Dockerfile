FROM nikolaik/python-nodejs:python3.11-nodejs20

USER root

# Instala dependencias do Chrome para o Puppeteer
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    ca-certificates \
    libnss3 \
    libxss1 \
    libasound2 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libgbm-dev \
    chromium \
    && rm -rf /var/lib/apt/lists/*

ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true \
    PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium

WORKDIR /app

# Instala dependencias Python (Site)
COPY requirements.txt .
RUN pip install -r requirements.txt

# Instala dependencias Node (Robos WPP e CHEP)
COPY whatsapp-bot/package*.json ./whatsapp-bot/
RUN cd whatsapp-bot && npm ci

# Copia todo o projeto
COPY . .

# Comando de inicio: Inicia o robo e o site juntos
CMD ["bash", "start.sh"]
