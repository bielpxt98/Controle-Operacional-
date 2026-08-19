require('dotenv').config({ path: '../.env' });
const { 
    default: makeWASocket, 
    initAuthCreds,
    makeCacheableSignalKeyStore,
    DisconnectReason, 
    downloadMediaMessage 
} = require('@whiskeysockets/baileys');
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

// ============================================================
// ============================================================
// SESSAO LOCAL (TESTE)
// ============================================================
const { useMultiFileAuthState } = require('@whiskeysockets/baileys');

// ============================================================
// CLASSIFICACAO COM GEMINI (contexto diferente por origem)
// ============================================================
async function classifyImage(buffer, textCaption, isFromGroup) {
    const model = genAI.getGenerativeModel({ model: "gemini-3.6-flash" });
    const groupPrompt = `Analise esta imagem de um GRUPO de motoristas de caminhao. Legenda: "${textCaption}"
Classifique:
1. 'CHEGADA': Foto da rua, volante, fachada, GPS indicando chegada no cliente.
2. 'NF_FINALIZADA': Nota Fiscal COM CARIMBO DE RECEBIDO ou ASSINATURA GRANDE indicando entrega finalizada.
3. 'NF_COLETA': Nota Fiscal LIMPA sem carimbo.
4. 'IRRELEVANTE': Qualquer outra coisa (memes, comida, texto).
Retorne JSON: { "tipo": "...", "motorista": null, "delivery": null, "cliente": null, "paletes": null }`;

    const privatePrompt = `Analise esta imagem de conversa PRIVADA. Legenda: "${textCaption}"
Classifique como 'ESCALA' SOMENTE se a imagem for uma tabela/planilha de programacao de coletas que contenha EXPLICITAMENTE colunas com nomes de MOTORISTAS e nomes de CLIENTES/DESTINOS.
Se nao tiver as duas informacoes claramente, classifique como 'IRRELEVANTE'.
Retorne JSON: { "tipo": "ESCALA" ou "IRRELEVANTE", "data_programacao": "DD/MM/AAAA", "dados_escala": [{"motorista": "LUIZ", "cliente": "JDE CAFE", "paletes": "476"}] }`;

    try {
        const result = await model.generateContent([isFromGroup ? groupPrompt : privatePrompt, { inlineData: { data: buffer.toString("base64"), mimeType: "image/jpeg" } }]);
        let text = result.response.text().replace(/```json/g, "").replace(/```/g, "").trim();
        return JSON.parse(text);
    } catch (error) {
        console.error("[GEMINI] Erro:", error.message);
        return null;
    }
}

// ============================================================
// LOGICA DE ESCALA (programacao de motoristas)
// ============================================================
const normalize = str => str.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toUpperCase().trim();

async function handleEscala(json) {
    if (!json.dados_escala || json.dados_escala.length === 0) return console.log("[ESCALA] Sem dados.");
    console.log("[ESCALA] Programacao para: " + json.data_programacao);
    const { data: coletas, error } = await supabase.from('deliveries').select('*').eq('data', json.data_programacao);
    if (error || !coletas?.length) return console.log("[ESCALA] Sem coletas no banco para " + json.data_programacao);

    for (let extraido of json.dados_escala) {
        const extraidoNorm = normalize(extraido.cliente);
        const extraidoWords = extraidoNorm.split(' ').filter(p => p.length > 3);
        let bestScore = 0, match = null;
        for (const c of coletas) {
            if (!c.cliente) continue;
            const dbNorm = normalize(c.cliente);
            const dbWords = dbNorm.split(' ').filter(p => p.length > 3);
            const score = extraidoWords.filter(p => dbNorm.includes(p)).length + dbWords.filter(p => extraidoNorm.includes(p)).length;
            if (score > bestScore) { bestScore = score; match = c; }
        }
        if (!match || bestScore === 0) { console.log("[ESCALA] Nao encontrado: " + extraido.cliente); continue; }
        let updateData = {};
        if (!match.motorista?.trim()) updateData.motorista = extraido.motorista;
        if ((!match.paletes || match.paletes == 0) && extraido.paletes) updateData.paletes = extraido.paletes;
        if (Object.keys(updateData).length > 0) {
            await supabase.from('deliveries').update(updateData).eq('id', match.id);
            console.log("✅ [ESCALA] " + match.cliente + " -> " + JSON.stringify(updateData));
        } else {
            console.log("ℹ️ [ESCALA] " + match.cliente + " ja preenchido.");
        }
    }
}

// ============================================================
// LOGICA DE MOTORISTA (chegada, coleta, finalizacao)
// ============================================================
async function handleMotorista(json, senderName) {
    if (!["CHEGADA", "NF_COLETA", "NF_FINALIZADA"].includes(json.tipo)) return;
    const { data: coletas, error } = await supabase.from('deliveries').select('*').order('id', { ascending: false }).limit(80);
    if (error) return console.error("[SUPABASE]", error);

    let coletaMatch = null;
    if (json.delivery) coletaMatch = coletas.find(c => String(c.delivery).includes(String(json.delivery)));
    if (!coletaMatch) {
        const nomeBuscado = normalize((json.motorista || senderName).replace("MOTORISTA", "").trim()).split(' ')[0];
        const coletasMotorista = coletas.filter(c => c.motorista && normalize(c.motorista).includes(nomeBuscado));
        if (coletasMotorista.length === 1) coletaMatch = coletasMotorista[0];
        else if (coletasMotorista.length > 1 && json.cliente) {
            const cNorm = normalize(json.cliente).split(' ')[0];
            coletaMatch = coletasMotorista.find(c => c.cliente && normalize(c.cliente).includes(cNorm)) || coletasMotorista[0];
        }
    }
    if (!coletaMatch) return console.log("[MOTORISTA] Nao encontrado para: " + senderName);

    const agora = new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', timeZone: 'America/Sao_Paulo' });
    let updateData = {};
    if (json.tipo === "CHEGADA")      { updateData.l_horario = agora; console.log("📍 " + coletaMatch.motorista + " CHEGOU as " + agora); }
    else if (json.tipo === "NF_COLETA")    { updateData.c_horario = agora; if (json.paletes) updateData.pc = Number(json.paletes); console.log("📦 " + coletaMatch.motorista + " COLETOU as " + agora); }
    else if (json.tipo === "NF_FINALIZADA") { updateData.f_horario = agora; console.log("🏁 " + coletaMatch.motorista + " FINALIZOU as " + agora); }
    if (Object.keys(updateData).length > 0) await supabase.from('deliveries').update(updateData).eq('id', coletaMatch.id);
}

// ============================================================
// WHATSAPP
// ============================================================
async function startWhatsApp() {
    const { state, saveCreds } = await useMultiFileAuthState("auth_info_baileys");
    const sock = makeWASocket({ auth: state, printQRInTerminal: false, logger: pino({ level: "silent" }), browser: ["Controle CHEP", "Chrome", "10.0.0"] });
    sock.ev.on('connection.update', async (update) => {
        const { connection, lastDisconnect, qr } = update;
        if (qr) { await qrcode.toFile(qrPath, qr); console.log("[WPP] QR Code gerado."); }
        if (connection === 'close') {
            if (fs.existsSync(qrPath)) fs.unlinkSync(qrPath);
            if (lastDisconnect.error?.output?.statusCode !== DisconnectReason.loggedOut) startWhatsApp();
        } else if (connection === 'open') {
            if (fs.existsSync(qrPath)) fs.unlinkSync(qrPath);
            console.log('[WPP] ✅ Conectado e pronto!');
        }
    });
    sock.ev.on('creds.update', saveCreds);
    sock.ev.on('messages.upsert', async (m) => {
        const msg = m.messages[0];
        if (!msg.message || msg.key.fromMe) return;
        const isFromGroup = msg.key.remoteJid?.endsWith('@g.us');
        const senderName = msg.pushName || "";
        const textCaption = msg.message.imageMessage?.caption || "";
        if (Object.keys(msg.message)[0] !== 'imageMessage') return;
        console.log("[WPP] Imagem de " + senderName + " (" + (isFromGroup ? "GRUPO" : "PRIVADO") + ")");
        const buffer = await downloadMediaMessage(msg, 'buffer', {}, { logger: pino({ level: "silent" }) });
        const json = await classifyImage(buffer, textCaption, isFromGroup);
        if (!json || json.tipo === "IRRELEVANTE") return console.log("[WPP] Imagem irrelevante, ignorando.");
        if (json.tipo === "ESCALA") await handleEscala(json);
        else if (isFromGroup) await handleMotorista(json, senderName);
    });
}
startWhatsApp();
