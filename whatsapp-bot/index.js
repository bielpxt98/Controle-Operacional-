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
const { updateChepOccurrence, runChepProgramacaoAmanha } = require('./chep.js');

const GEMINI_API_KEY = process.env.GEMINI_API_KEY || "COLOQUE_SUA_CHAVE_AQUI";
const SUPABASE_URL = process.env.SUPABASE_URL || "https://zkqzejnflpzknuuirlav.supabase.co";
const SUPABASE_KEY = process.env.SUPABASE_KEY || "sb_publishable_8pSOHjRSllI9wWVYPkmYFA_AfzxV-QS";

const supabase = createClient(SUPABASE_URL, SUPABASE_KEY);
const genAI = new GoogleGenerativeAI(GEMINI_API_KEY);
const qrPath = path.join(__dirname, '..', 'static', 'qr.png');

// ============================================================
// ============================================================
// SESSAO LOCAL
// ============================================================
const { useMultiFileAuthState } = require('@whiskeysockets/baileys');

async function startWhatsApp() {
    const { state, saveCreds } = await useMultiFileAuthState('auth_info_baileys');
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
        }
    });
    sock.ev.on('creds.update', saveCreds);
    sock.ev.on('messages.upsert', async (m) => {
        const msg = m.messages[0];
        if (!msg.message || msg.key.fromMe) return;
        const isFromGroup = msg.key.remoteJid?.endsWith('@g.us');
        
        if (isFromGroup) {
            try {
                const groupMeta = await sock.groupMetadata(msg.key.remoteJid);
                const groupName = groupMeta.subject || "";
                if (!groupName.toLowerCase().includes("purm salvador")) {
                    return; // Ignora se não for o grupo correto
                }
            } catch(e) { return; }
        }

        const senderName = msg.pushName || "";
        const textCaption = msg.message.imageMessage?.caption || "";
        if (Object.keys(msg.message)[0] !== 'imageMessage') return;
        const remetenteNum = msg.key.participant || msg.key.remoteJid;
        
        // ================= REGRAS DE LEITURA =================
        const numA = "558194346196";
        const numB = "5581994346196"; 
        const numC = "558183493082";
        const numD = "5581983493082";
        const nomeDela = "luciana ribeiro";
        
        const nomeRemetenteLower = senderName.toLowerCase();
        const msgDaProgramacao = remetenteNum.includes(numA) || remetenteNum.includes(numB) || remetenteNum.includes(numC) || remetenteNum.includes(numD) || nomeRemetenteLower.includes(nomeDela) || nomeRemetenteLower.includes("luciana");

        // Se for mensagem no PRIVADO, SÓ PODE SER DESSES DOIS NUMEROS (que enviam a programacao)
        if (!isFromGroup && !msgDaProgramacao) {
             console.log("[WPP] -> Ignorado: Mensagem privada de " + senderName + " (" + remetenteNum + "), não é um número autorizado para programação.");
             return;
        }
        // Se for no GRUPO PURM SALVADOR, aceitamos mensagens de QUALQUER UM (para os comandos hlocal, hcoletado, etc)
        // =====================================================
        
        console.log("[WPP] -> ATENÇÃO! Nova imagem recebida de DONA LUCIANA:");
        console.log("[WPP] -> NOME: " + senderName);
        console.log("[WPP] -> NUMERO/ID: " + remetenteNum);
        console.log("[WPP] -> FONTE: " + (isFromGroup ? "GRUPO PURM SALVADOR" : "PRIVADO"));
        const buffer = await downloadMediaMessage(msg, 'buffer', {}, { logger: pino({ level: "silent" }) });
        const json = await classifyImage(buffer, textCaption, isFromGroup);
        if (!json || json.tipo === "IRRELEVANTE") return console.log("[WPP] Imagem irrelevante, ignorando.");
        
        if (json.tipo === "ESCALA") {
            await handleEscala(json);
        } else {
            // Se for do privado (e passou pela trava), é a programação (motorista + delivery)
            if (!isFromGroup) {
                await handleMotorista(json, senderName);
            } else {
                // Se for do grupo, é o motorista mandando a foto da NF (hlocal, hcoletado, hfinalizado)
                // Vamos mandar para o handleMotorista por enquanto para extrair e salvar, 
                // e em breve implementamos a logica exata de mudar os status.
                await handleMotorista(json, senderName);
            }
        }
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

// INICIA O LOOP DA CHEP DE FORMA INDEPENDENTE DO WPP
iniciarLoopCHEP();