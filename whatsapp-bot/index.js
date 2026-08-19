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
const JSZip = require('jszip');
const path = require('path');
const { GoogleGenerativeAI } = require('@google/generative-ai');
const { createClient } = require('@supabase/supabase-js');
const { updateChepOccurrence, runChepProgramacaoAmanha } = require('./chep.js');

const GEMINI_API_KEY = process.env.GEMINI_API_KEY || "COLOQUE_SUA_CHAVE_AQUI";
const SUPABASE_URL = process.env.SUPABASE_URL || "https://zkqzejnflpzknuuirlav.supabase.co";
const SUPABASE_KEY = process.env.SUPABASE_KEY || "sb_publishable_8pSOHjRSllI9wWVYPkmYFA_AfzxV-QS";

const supabase = createClient(SUPABASE_URL, SUPABASE_KEY);
const genAI = new GoogleGenerativeAI(GEMINI_API_KEY);
const qrPath = path.join(__dirname, '..', 'static', 'qr.png');

// ============================================================
// ============================================================
// SESSAO HIBRIDA (LOCAL + BACKUP NO SUPABASE)
// ============================================================
const { useMultiFileAuthState } = require('@whiskeysockets/baileys');
const JSZip = require('jszip');

async function useHybridAuthState() {
    // 1. Tenta baixar o backup do Supabase
    try {
        const { data } = await supabase.from('whatsapp_session').select('value').eq('key', 'backup_zip').single();
        if (data && data.value) {
            console.log("[SESSAO] Restaurando backup do Supabase...");
            const zip = new JSZip();
            const zipBuffer = Buffer.from(data.value, 'base64');
            await zip.loadAsync(zipBuffer);
            if (!fs.existsSync('auth_info_baileys')) fs.mkdirSync('auth_info_baileys');
            for (const filename of Object.keys(zip.files)) {
                const fileData = await zip.file(filename).async('nodebuffer');
                fs.writeFileSync('auth_info_baileys/' + filename, fileData);
            }
            console.log("[SESSAO] Backup restaurado com sucesso!");
        }
    } catch (e) { console.log("[SESSAO] Nenhum backup anterior encontrado (Normal)."); }

    const { state, saveCreds } = await useMultiFileAuthState('auth_info_baileys');
    
    let isBackingUp = false;
    let needsBackup = false;

    const doBackup = async () => {
        if (isBackingUp || !fs.existsSync('auth_info_baileys')) return;
        isBackingUp = true;
        needsBackup = false;
        try {
            const zip = new JSZip();
            const files = fs.readdirSync('auth_info_baileys');
            for (const f of files) {
                zip.file(f, fs.readFileSync('auth_info_baileys/' + f));
            }
            const content = await zip.generateAsync({ type: 'base64' });
            await supabase.from('whatsapp_session').upsert({ key: 'backup_zip', value: content }, { onConflict: 'key' });
        } catch (e) { console.error("[SESSAO] Erro no backup:", e.message); }
        isBackingUp = false;
        if (needsBackup) setTimeout(doBackup, 10000);
    };

    const saveCredsAndBackup = async () => {
        await saveCreds();
        needsBackup = true;
        setTimeout(doBackup, 5000); // Debounce de 5 seg
    };

    return { state, saveCreds: saveCredsAndBackup };
}
    async function startWhatsApp() {
    const { state, saveCreds } = await useHybridAuthState();
    const sock = makeWASocket({ auth: state, printQRInTerminal: false, logger: pino({ level: "silent" }), browser: ["Controle CHEP", "Chrome", "10.0.0"] });
    sock.ev.on('connection.update', async (update) => {
        const { connection, lastDisconnect, qr } = update;
        if (qr) { await qrcode.toFile(qrPath, qr); console.log("[WPP] QR Code gerado."); }
        if (connection === 'close') {
            if (fs.existsSync(qrPath)) fs.unlinkSync(qrPath);
            if (lastDisconnect.error?.output?.statusCode !== DisconnectReason.loggedOut) startWhatsApp();
        } else if (connection === 'open') {
            if (fs.existsSync(qrPath)) fs.unlinkSync(qrPath);
            console.log('[WPP] Conectado e pronto!');
            // INICIA O LOOP DA CHEP
            iniciarLoopCHEP();
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

let chepRodando = false;
async function iniciarLoopCHEP() {
    setInterval(async () => {
        if (chepRodando) return;
        chepRodando = true;
        try {
            console.log("[CHEP-LOOP] Buscando entregas prontas para preencher na CHEP...");
            const hoje = new Date();
            const mesAtual = hoje.getMonth() + 1;
            const diaAmanha = (hoje.getDate() + 1).toString().padStart(2, '0');
            const mesAmanha = mesAtual.toString().padStart(2, '0');
            const dataAmanha = diaAmanha + '/' + mesAmanha; // Ex: 20/08
            
            const { data, error } = await supabase
                .from('deliveries')
                .select('*')
                .ilike('data', `%${dataAmanha}%`)
                .not('motorista', 'is', null)
                .is('status_chep', null);
            
            if (error) { console.error("Erro banco:", error); }
            else if (data && data.length > 0) {
                console.log(`[CHEP-LOOP] Achei ${data.length} entregas! Iniciando Robô CHEP...`);
                await runChepProgramacaoAmanha(data);
            } else {
                console.log("[CHEP-LOOP] Nada pendente para amanha.");
            }
        } catch(e) { console.error("Erro no loop CHEP:", e); }
        chepRodando = false;
    }, 10 * 60 * 1000); // Roda a cada 10 minutos
    
    // E roda uma vez agora na inicializacao
    if(!chepRodando){
      setTimeout(async () => {
          chepRodando = true;
          try {
              const hoje = new Date();
              const mesAtual = hoje.getMonth() + 1;
              const diaAmanha = (hoje.getDate() + 1).toString().padStart(2, '0');
              const mesAmanha = mesAtual.toString().padStart(2, '0');
              const dataAmanha = diaAmanha + '/' + mesAmanha;
              
              const { data } = await supabase.from('deliveries').select('*').ilike('data', `%${dataAmanha}%`).not('motorista', 'is', null).is('status_chep', null);
              if (data && data.length > 0) { await runChepProgramacaoAmanha(data); }
          } catch(e) {}
          chepRodando = false;
      }, 5000);
    }
}
startWhatsApp();
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
