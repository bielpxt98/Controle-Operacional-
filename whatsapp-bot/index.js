require('dotenv').config({ path: '../.env' });
const { default: makeWASocket, useMultiFileAuthState, DisconnectReason, downloadMediaMessage } = require('@whiskeysockets/baileys');
const pino = require('pino');
const qrcode = require('qrcode');
const fs = require('fs');
const path = require('path');
const { GoogleGenerativeAI } = require('@google/generative-ai');
const { createClient } = require('@supabase/supabase-js');

const GEMINI_API_KEY = process.env.GEMINI_API_KEY || "COLOQUE_SUA_CHAVE_AQUI";
const SUPABASE_URL = process.env.SUPABASE_URL || "https://zkqzejnflpzknuuirlav.supabase.co";
const SUPABASE_KEY = process.env.SUPABASE_KEY || "sb_publishable_8pSOHjRSllI9wWVYPkmYFA_AfzxV-QS";

const supabase = createClient(SUPABASE_URL, SUPABASE_KEY);
const genAI = new GoogleGenerativeAI(GEMINI_API_KEY);
const qrPath = path.join(__dirname, '..', 'static', 'qr.png');

async function processImageWithGemini(buffer, textCaption) {
    console.log("[GEMINI] Analisando imagem do motorista...");
    const model = genAI.getGenerativeModel({ model: "gemini-1.5-flash" });
    const prompt = `Analise esta imagem que um motorista enviou. Legenda: ${textCaption}

Regras (campo 'tipo'):
1. 'CHEGADA': Foto da rua, volante, fachada, ou localizacao GPS indicando chegada.
2. 'NF_FINALIZADA': Nota Fiscal (NF) ou comprovante COM CARIMBO DE RECEBIDO ou ASSINATURA GRANDE no meio/fim.
3. 'NF_COLETA': Nota Fiscal (NF) LIMPA, sem carimbo de recebido.
4. 'ESCALA': Tabela de escala (MOTORISTA, CLIENTE, PALETES).
5. 'IRRELEVANTE': Memes, figurinhas, comida.

Retorne JSON: {
  "tipo": "CHEGADA" | "NF_FINALIZADA" | "NF_COLETA" | "ESCALA" | "IRRELEVANTE",
  "motorista": "Nome legível ou null",
  "delivery": "Número de 10 dígitos (ex: 3788438763) escrito na NF ou null",
  "cliente": "Nome do destino (ex: YOKI, ASSAI) ou null",
  "paletes": "Quantidade (número). Busque na legenda ou NF, senão null",
  "dados_escala": [{"motorista": "LUIZ", "cliente": "JDE CAFE"}]
}
Apenas o JSON bruto sem markdown.`;

    try {
        const result = await model.generateContent([prompt, { inlineData: { data: buffer.toString("base64"), mimeType: "image/jpeg" } }]);
        const response = await result.response;
        let text = response.text().replace(/```json/g, "").replace(/```/g, "").trim();
        return JSON.parse(text);
    } catch (error) {
        console.error("[GEMINI] Erro:", error);
        return null;
    }
}

async function handleLogic(json, senderName) {
    if (!json || json.tipo === "IRRELEVANTE") return;

    const { data: coletas, error } = await supabase.from('deliveries').select('*').order('id', { ascending: false }).limit(80);
    if (error) return console.error("[SUPABASE] Erro:", error);

    if (json.tipo === "ESCALA" && json.dados_escala) {
        for (let extraido of json.dados_escala) {
            let match = coletas.find(c => c.cliente && c.cliente.toUpperCase().split(' ').some(p => p.length > 3 && extraido.cliente.toUpperCase().includes(p)));
            if (match) await supabase.from('deliveries').update({ motorista: extraido.motorista }).eq('id', match.id);
        }
        return;
    }

    let coletaMatch = null;
    if (json.delivery) coletaMatch = coletas.find(c => String(c.delivery).includes(String(json.delivery)));
    
    if (!coletaMatch) {
        let nomeBuscado = (json.motorista || senderName).toUpperCase().replace(" MOTORISTA", "").trim();
        let coletasMotorista = coletas.filter(c => c.motorista && c.motorista.toUpperCase().includes(nomeBuscado.split(' ')[0]));
        
        if (coletasMotorista.length === 1) coletaMatch = coletasMotorista[0];
        else if (coletasMotorista.length > 1 && json.cliente) {
            coletaMatch = coletasMotorista.find(c => c.cliente && c.cliente.toUpperCase().includes(json.cliente.toUpperCase().split(' ')[0])) || coletasMotorista[0];
        }
    }

    if (!coletaMatch) return console.log("[LOGICA] Coleta nao encontrada.");

    const agora = new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', timeZone: 'America/Sao_Paulo' });
    let updateData = {};

    if (json.tipo === "CHEGADA") updateData.l_horario = agora;
    else if (json.tipo === "NF_COLETA") { updateData.c_horario = agora; if (json.paletes) updateData.pc = Number(json.paletes); }
    else if (json.tipo === "NF_FINALIZADA") { updateData.f_horario = agora; console.log("GATILHO CHEP"); }

    if (Object.keys(updateData).length > 0) await supabase.from('deliveries').update(updateData).eq('id', coletaMatch.id);
}

async function startWhatsApp() {
    const { state, saveCreds } = await useMultiFileAuthState('auth_info_baileys');
    const sock = makeWASocket({ auth: state, printQRInTerminal: true, logger: pino({ level: "silent" }) });

    sock.ev.on('connection.update', async (update) => {
        const { connection, lastDisconnect, qr } = update;
        if (qr) await qrcode.toFile(qrPath, qr);
        if (connection === 'close') {
            if (fs.existsSync(qrPath)) fs.unlinkSync(qrPath);
            if (lastDisconnect.error?.output?.statusCode !== DisconnectReason.loggedOut) startWhatsApp();
        } else if (connection === 'open') {
            if (fs.existsSync(qrPath)) fs.unlinkSync(qrPath);
        }
    });
    sock.ev.on('creds.update', saveCreds);

    sock.ev.on('messages.upsert', async (m) => {
        const msg = m.messages[0];
        if (!msg.message || msg.key.fromMe) return;

        const senderName = msg.pushName || "";
        const textCaption = msg.message.imageMessage?.caption || "";

        if (Object.keys(msg.message)[0] === 'imageMessage') {
            const buffer = await downloadMediaMessage(msg, 'buffer', {}, { logger: pino({ level: "silent" }) });
            const json = await processImageWithGemini(buffer, textCaption);
            if (json) await handleLogic(json, senderName);
        }
    });
}
startWhatsApp();
