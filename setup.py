import os

js_code = '''require('dotenv').config({ path: '../.env' });
const { default: makeWASocket, useMultiFileAuthState, DisconnectReason, downloadMediaMessage } = require('@whiskeysockets/baileys');
const pino = require('pino');
const qrcode = require('qrcode');
const fs = require('fs');
const path = require('path');
const { GoogleGenerativeAI } = require('@google/generative-ai');
const { createClient } = require('@supabase/supabase-js');

const TARGET_SENDER = "Dona Luciana";
const GEMINI_API_KEY = process.env.GEMINI_API_KEY || "COLOQUE_SUA_CHAVE_AQUI";
const SUPABASE_URL = process.env.SUPABASE_URL || "https://zkqzejnflpzknuuirlav.supabase.co";
const SUPABASE_KEY = process.env.SUPABASE_KEY || "sb_publishable_8pSOHjRSllI9wWVYPkmYFA_AfzxV-QS";

const supabase = createClient(SUPABASE_URL, SUPABASE_KEY);
const genAI = new GoogleGenerativeAI(GEMINI_API_KEY);

const qrPath = path.join(__dirname, '..', 'static', 'qr.png');

async function processImageWithGemini(buffer) {
    console.log("[GEMINI] Analisando imagem...");
    const model = genAI.getGenerativeModel({ model: "gemini-1.5-flash" });
    const prompt = Analise esta imagem que contém uma escala de motoristas e clientes.
Retorne APENAS um JSON válido no formato de array de objetos.
Cada objeto deve ter:
- "motorista": O nome do motorista (ex: LUIZ, GABRIEL, WILSON, FABIO, VALDEMIR, JONES, ARGEMIRO)
- "cliente": O nome do cliente ou destino (ex: JDE CAFE, DISTRIBUIDORA SANTA CRUZ, ASSAI, WMS MAX ATACADO, CABRAL E SOUSA, YOKI)
Não inclua marcações markdown, apenas o JSON bruto.;

    try {
        const result = await model.generateContent([prompt, { inlineData: { data: buffer.toString("base64"), mimeType: "image/jpeg" } }]);
        const response = await result.response;
        let text = response.text().replace(/\\\json/g, "").replace(/\\\/g, "").trim();
        return JSON.parse(text);
    } catch (error) {
        console.error("[GEMINI] Erro:", error);
        return null;
    }
}

async function updateSupabase(extractedData) {
    const { data: coletas, error } = await supabase.from('deliveries').select('*').order('id', { ascending: false }).limit(50);
    if (error) return console.error("[SUPABASE] Erro:", error);

    for (let extraido of extractedData) {
        let coletaMatch = coletas.find(c => c.cliente && c.cliente.toUpperCase().split(' ').some(p => p.length > 3 && extraido.cliente.toUpperCase().includes(p)));
        if (coletaMatch) {
            await supabase.from('deliveries').update({ motorista: extraido.motorista }).eq('id', coletaMatch.id);
            console.log(✅  -> );
        }
    }
    console.log("🚀 [GATILHO CHEP] Aqui ativaria o robô local!");
}

async function startWhatsApp() {
    const { state, saveCreds } = await useMultiFileAuthState('auth_info_baileys');
    const sock = makeWASocket({ auth: state, printQRInTerminal: true, logger: pino({ level: "silent" }) });

    sock.ev.on('connection.update', async (update) => {
        const { connection, lastDisconnect, qr } = update;
        if (qr) {
            await qrcode.toFile(qrPath, qr);
            console.log("[WPP] QR Code salvo em static/qr.png");
        }
        if (connection === 'close') {
            if (fs.existsSync(qrPath)) fs.unlinkSync(qrPath);
            const shouldReconnect = lastDisconnect.error?.output?.statusCode !== DisconnectReason.loggedOut;
            if (shouldReconnect) startWhatsApp();
        } else if (connection === 'open') {
            console.log('[WPP] ✅ Conectado!');
            if (fs.existsSync(qrPath)) fs.unlinkSync(qrPath);
        }
    });
    sock.ev.on('creds.update', saveCreds);

    sock.ev.on('messages.upsert', async (m) => {
        const msg = m.messages[0];
        if (!msg.message || msg.key.fromMe) return;
        if ((msg.pushName || "") !== TARGET_SENDER) return;

        if (Object.keys(msg.message)[0] === 'imageMessage') {
            const buffer = await downloadMediaMessage(msg, 'buffer', {}, { logger: pino({ level: "silent" }) });
            const json = await processImageWithGemini(buffer);
            if (json) await updateSupabase(json);
        }
    });
}
startWhatsApp();
'''

with open('whatsapp-bot/index.js', 'w', encoding='utf-8') as f:
    f.write(js_code)

with open('app.py', 'r', encoding='utf-8') as f:
    app_py = f.read()

qr_route = '''
@app.route("/whatsapp")
def whatsapp_qr():
    import os
    qr_path = os.path.join(app.static_folder, "qr.png")
    if os.path.exists(qr_path):
        return "<h1>Conecte o WhatsApp</h1><p>Escaneie o QR Code abaixo:</p><img src='/static/qr.png' /><p>Atualize a página em 10 seg.</p>"
    return "<h1>✅ WhatsApp Conectado ou Iniciando...</h1>"
'''
if "def whatsapp_qr()" not in app_py:
    app_py = app_py.replace('if __name__ == "__main__":', qr_route + '\nif __name__ == "__main__":')
    with open('app.py', 'w', encoding='utf-8') as f:
        f.write(app_py)

start_sh = '''#!/bin/bash
cd whatsapp-bot
npm install
node index.js &
cd ..
gunicorn app:app
'''
with open('start.sh', 'w', encoding='utf-8', newline='\\n') as f:
    f.write(start_sh)

with open('Procfile', 'w', encoding='utf-8') as f:
    f.write('web: bash start.sh')

print("Done")
