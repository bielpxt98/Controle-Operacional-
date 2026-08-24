
// ==========================================
// FILTRO DE LIXO DO BAILEYS / LIBSIGNAL
// ==========================================
const originalConsoleError = console.error;
console.error = function(...args) {
    if (args.length > 0 && typeof args[0] === 'string' && (args[0].includes('Bad MAC') || args[0].includes('Session error'))) return;
    originalConsoleError.apply(console, args);
};
const originalConsoleLog = console.log;
console.log = function(...args) {
    if (args.length > 0 && typeof args[0] === 'string' && (args[0].includes('Bad MAC') || args[0].includes('Session error'))) return;
    originalConsoleLog.apply(console, args);
};


// ==========================================
// CONFIGURACAO DE LOGS COM HORARIO
// ==========================================
const originalLog = console.log;
console.log = function() {
    const agora = new Date().toLocaleString('pt-BR', { timeZone: 'America/Sao_Paulo' });
    const args = Array.from(arguments);
    args.unshift(`[${agora}]`);
    originalLog.apply(console, args);
};

console.log("==========================================");
console.log("🚀 ROBÔ REINICIADO / CÓDIGO ATUALIZADO 🚀");
console.log("==========================================");

const ws = require('ws');
global.WebSocket = ws;
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
    if (!msg.message) return; // Removida a trava fromMe para permitir que o próprio dono ative os gatilhos
    
    
    const isFromGroup = msg.key.remoteJid?.endsWith('@g.us');
    console.log(`[WPP-DEBUG] Mensagem recebida de ${msg.pushName} no JID ${msg.key.remoteJid}`);

    let groupName = "";
    
    if (isFromGroup) {
        try {
            const groupMeta = await sock.groupMetadata(msg.key.remoteJid);
            groupName = groupMeta.subject || "";
            
            if (!groupName.toLowerCase().includes("purm salvador")) {
                console.log(`[WPP-DEBUG] Ignorando grupo: ${groupName}`);
                return;
            }

        } catch(e) { console.error(`[WPP-DEBUG] Erro groupMetadata:`, e.message); return; }
    }

    const senderName = msg.pushName || "";
    const remetenteNum = msg.key.participant || msg.key.remoteJid;
    
    const txtMsg = msg.message.conversation || msg.message.extendedTextMessage?.text || "";
    const captionMsg = msg.message.imageMessage?.caption || "";
    const textoCompleto = (txtMsg + " " + captionMsg).toLowerCase();
    const quotedMsg = msg.message.extendedTextMessage?.contextInfo?.quotedMessage;
    
    const numA = "558194346196";
    const numB = "5581994346196"; 
    const numC = "558183493082";
    const numD = "5581983493082";
    const numE = "558193792908"; // Gabriel Peixoto
    const isAdmin = remetenteNum.includes(numA) || remetenteNum.includes(numB) || remetenteNum.includes(numC) || remetenteNum.includes(numD) || remetenteNum.includes(numE) || senderName.toLowerCase().includes("luciana") || senderName.toLowerCase().includes("osvaldo");

    // =========================================================
    // 1. MENSAGEM NO PRIVADO
    // =========================================================
    if (!isFromGroup) {
        if (!isAdmin) return; 
        if (!msg.message.imageMessage) return; 
        
        console.log("[WPP-PRIVADO] Nova imagem de programacao de " + senderName);
        const { downloadMediaMessage } = require('@whiskeysockets/baileys');
        const pino = require('pino');
        const buffer = await downloadMediaMessage(msg, 'buffer', {}, { logger: pino({ level: "silent" }) });
        const json = await classifyImage(buffer, captionMsg, isFromGroup);
        if (json && json.tipo === "PROGRAMACAO") {
            await handleMotorista(json, senderName);
        }
        return;
    }

    // =========================================================
    // 2. MENSAGENS NO GRUPO (PURM SALVADOR)
    // =========================================================
    
    let motoristaPrimeiroNome = senderName.split(' ')[0].toUpperCase();
    motoristaPrimeiroNome = motoristaPrimeiroNome.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
    if (motoristaPrimeiroNome.includes("GABRIEL")) motoristaPrimeiroNome = "GABRIEL";
    if (motoristaPrimeiroNome === "BORGES") motoristaPrimeiroNome = "ARGEMIRO"; // "borges filho" -> ARGEMIRO
    
    const hojeObj = new Date();
    const dataHojeCurta = hojeObj.getDate().toString().padStart(2, '0') + '/' + (hojeObj.getMonth() + 1).toString().padStart(2, '0');
    const formatterHora = new Intl.DateTimeFormat('pt-BR', { timeZone: 'America/Sao_Paulo', hour: '2-digit', minute: '2-digit', hour12: false });
    const horaAtual = formatterHora.format(new Date());

    const deliveryMatch = txtMsg.match(/\b\d{10}\b/);
    if (deliveryMatch && quotedMsg && quotedMsg.imageMessage) {
        const numeroDelivery = deliveryMatch[0];
        const legendaOriginal = quotedMsg.imageMessage.caption || "";
        let paletesNumStr = "N/A";
        const updatePayload = { c_horario: horaAtual };
        let extractedNum = null;
        
        let matchSufixo = legendaOriginal.match(/(\d+)\s*(?:palet|un|und|p\b|cx|peca|peça)/i);
        if (matchSufixo) {
            extractedNum = parseInt(matchSufixo[1]);
        } else {
            let fallbackSoNumero = legendaOriginal.match(/^\s*(\d+)\s*$/);
            if (fallbackSoNumero) {
                extractedNum = parseInt(fallbackSoNumero[1]);
            } else {
                let fallbackPrimeiro = legendaOriginal.match(/\b(\d{1,4})\b/);
                if (fallbackPrimeiro) extractedNum = parseInt(fallbackPrimeiro[1]);
            }
        }
        
        if (extractedNum !== null) {
            updatePayload.pc = extractedNum;
            paletesNumStr = extractedNum.toString();
        }
        
        console.log(`[WPP-GRUPO] H_COLETADO detectado. Delivery: ${numeroDelivery}, Paletes: ${paletesNumStr}`);
        const { error } = await supabase.from('deliveries').update(updatePayload).eq('delivery', numeroDelivery);
        if (!error) await sock.sendMessage('558193792908@s.whatsapp.net', { text: `📦 H_COLETADO marcado! Delivery: ${numeroDelivery} | Paletes: ${paletesNumStr}` });
        return;
    }

    const isLocation = !!msg.message.locationMessage || !!msg.message.liveLocationMessage;
    

    if (isLocation && !isAdmin) {
        console.log(`[WPP-GRUPO] H_LOCAL detectado para o motorista ${motoristaPrimeiroNome}`);
        const { data: pendentes } = await supabase.from('deliveries').select('id').ilike('motorista', `%${motoristaPrimeiroNome}%`).ilike('data', `%${dataHojeCurta}%`).is('l_horario', null).not('delivery', 'ilike', '340%').order('id', { ascending: true }).limit(1);
        if (pendentes && pendentes.length > 0) {
            await supabase.from('deliveries').update({ l_horario: horaAtual }).eq('id', pendentes[0].id);
            await sock.sendMessage('558193792908@s.whatsapp.net', { text: `📍 H_LOCAL marcado para ${motoristaPrimeiroNome} (${horaAtual})` });
            console.log(`[WPP-GRUPO] H_LOCAL marcado no banco! (${horaAtual})`);
        } else {
            console.log(`[WPP-GRUPO] FALHA: Nenhuma carga vazia (l_horario=null) achada para motorista=${motoristaPrimeiroNome} na data=${dataHojeCurta}`);
        }
        return;
    }

    if (msg.message.imageMessage && !deliveryMatch && !isAdmin) {
        console.log(`[WPP-GRUPO] Foto enviada por ${motoristaPrimeiroNome}. Analisando se é NF Carimbada...`);
        const { downloadMediaMessage } = require('@whiskeysockets/baileys');
        const pino = require('pino');
        const buffer = await downloadMediaMessage(msg, 'buffer', {}, { logger: pino({ level: "silent" }) });
        const json = await classifyImage(buffer, captionMsg, isFromGroup);
        if (json && json.tipo === "NF_ASSINADA") {
            const clienteLimpo = (json.cliente || "").toUpperCase().trim();
            const deliveryLido = json.delivery || "";
            console.log(`[WPP-GRUPO] NF ASSINADA! Cliente: ${clienteLimpo} | Delivery: ${deliveryLido}`);
            
            let query = supabase.from('deliveries').select('id').ilike('motorista', `%${motoristaPrimeiroNome}%`).is('f_horario', null);
            
            if (deliveryLido && String(deliveryLido).length === 10) {
                query = query.eq('delivery', String(deliveryLido));
            } else {
                query = query.ilike('data', `%${dataHojeCurta}%`).ilike('clientes', `%${clienteLimpo}%`);
            }
            const { data: finalizaveis } = await query.limit(1);
            if (finalizaveis && finalizaveis.length > 0) {
                await supabase.from('deliveries').update({ f_horario: horaAtual, status: 'CONCLUIDO' }).eq('id', finalizaveis[0].id);
                await sock.sendMessage('558193792908@s.whatsapp.net', { text: `✅ H_FINALIZADO marcado! Cliente: ${clienteLimpo} | Delivery: ${deliveryLido}` });
                console.log(`[WPP-GRUPO] H_FINALIZADO marcado!`);
            } else {
                console.log(`[WPP-GRUPO] FALHA: Nenhuma carga aberta achada para motorista=${motoristaPrimeiroNome}, cliente=${clienteLimpo}, data=${dataHojeCurta}`);
            }
        }
        return;
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


// ==========================================
// CÉREBRO IA: GEMINI VISION + SUPABASE
// ==========================================

async function classifyImage(buffer, textCaption, isFromGroup) {
    try {
        console.log("[GEMINI] Analisando imagem recebida...");
        const model = genAI.getGenerativeModel({ model: "gemini-2.5-flash" });
        
        let prompt = "";
        if (isFromGroup) {
            prompt = `Analise a imagem em anexo, que é um documento enviado por um motorista.
Regras:
1. Verifique se a imagem contém carimbos de recebimento, assinaturas grandes confirmando a entrega, ou textos manuscritos como 'recebido'. Se SIM, isso indica que a carga foi FINALIZADA.
2. Neste caso, extraia a PRIMEIRA PALAVRA PRINCIPAL do nome do cliente (ex: "ASSAI", "ATACADAO", "WMS"). ATENÇÃO ÀS REMESSAS: Se a nota tiver carimbo da "JACOBS", "DOUWE EGBERTS" ou "JDE", preencha o cliente como "JDE". Se tiver "JSL", preencha "JSL". Se tiver "BOOMIX", preencha "BOOMIX". E também PROCURE POR UM NÚMERO DE DELIVERY manuscrito.
3. O número do Delivery é frequentemente escrito à mão (manuscrito) na nota e contém EXATAMENTE 10 dígitos (geralmente começando com 37 ou 34). Exemplo: 3788446193.
4. Se encontrar o número do Delivery na imagem, inclua-o no JSON.
5. Devolva EXATAMENTE no formato JSON: {"tipo": "NF_ASSINADA", "cliente": "PRIMEIRA_PALAVRA_CLIENTE", "delivery": "NUMERO_DE_10_DIGITOS"} (Se não achar o delivery, mande null).
6. Se a imagem não tiver carimbos/assinaturas de conclusão, devolva: {"tipo": "IRRELEVANTE"}`;
        } else {
            prompt = `Analise a imagem em anexo. Ela é uma tabela de programação de cargas diárias.
Extraia os dados em formato JSON estrito, sem formatação markdown.
Regras:
1. Extraia o nome do motorista.
2. Na coluna de destino, extraia apenas a PRIMEIRA PALAVRA PRINCIPAL do nome do cliente (em maiúsculas).
3. Extraia também a quantidade de paletes (um número).
4. Devolva no seguinte formato JSON: {"tipo": "PROGRAMACAO", "entregas": [{"motorista": "NOME DO MOTORISTA", "primeiro_nome_cliente": "PRIMEIRA_PALAVRA_CLIENTE", "paletes": 476}]}
5. Pode haver mais de uma entrega, coloque todas no array "entregas".
6. Se não for tabela, devolva apenas: {"tipo": "IRRELEVANTE"}
Responda APENAS com o JSON.`;
        }

        const imagePart = {
            inlineData: {
                data: buffer.toString("base64"),
                mimeType: "image/jpeg"
            }
        };

        const resultPromise = model.generateContent([prompt, imagePart]);
        const timeoutPromise = new Promise((_, reject) => setTimeout(() => reject(new Error("Timeout: Gemini demorou mais de 40 segundos para responder.")), 40000));
        const result = await Promise.race([resultPromise, timeoutPromise]);
        const responseText = result.response.text();
        
        let cleanJson = responseText.replace(/```json/g, '').replace(/```/g, '').trim();
        const json = JSON.parse(cleanJson);
        console.log("[GEMINI] Resultado:", JSON.stringify(json));
        return json;
    } catch(e) {
        console.error("[GEMINI] Erro na classificacao da imagem:", e.message);
        return { tipo: "IRRELEVANTE" };
    }
}

async function handleEscala(json) {}

async function handleMotorista(json, senderName) {
    if (!json.entregas || !Array.isArray(json.entregas)) return;
    
    console.log(`[WPP] Processando ${json.entregas.length} entregas identificadas pela IA...`);
    
    const hoje = new Date();
    const mesAtual = hoje.getMonth() + 1;
    const diaAmanha = (hoje.getDate() + 1).toString().padStart(2, '0');
    const mesAmanha = mesAtual.toString().padStart(2, '0');
    const dataAmanhaCurta = diaAmanha + '/' + mesAmanha; // 21/08
    
    for (const entrega of json.entregas) {
        if (!entrega.motorista || !entrega.primeiro_nome_cliente) continue;
        
        const clienteBusca = String(entrega.primeiro_nome_cliente).toUpperCase().trim();
        const motoristaFormatado = String(entrega.motorista).toUpperCase().trim();
        const paletes = Number(entrega.paletes) || 0;
        
        console.log(`[WPP] Buscando no banco: Cliente '${clienteBusca}' com ${paletes} paletes para o motorista ${motoristaFormatado}...`);
        
        // Busca flexível: Cliente que contém a palavra E quantidade de paletes idêntica E que a data contém amanhã
        const { data: encontrados, error } = await supabase
            .from('deliveries')
            .select('*')
            .ilike('data', `%${dataAmanhaCurta}%`)
            .ilike('clientes', `%${clienteBusca}%`)
            .eq('paletes', paletes)
            .is('motorista', null); // So preenche se estiver vazio, evita sobrescrever errados
            
        if (encontrados && encontrados.length > 0) {
             const alvo = encontrados[0];
             console.log(`[WPP] MATCH PERFEITO! Atribuindo Delivery ${alvo.delivery} ao motorista ${motoristaFormatado}...`);
             await supabase.from('deliveries').update({ motorista: motoristaFormatado }).eq('id', alvo.id);
        } else {
             console.log(`[WPP] AVISO: Nao encontrei entrega vazia para amanha do cliente '${clienteBusca}' com ${paletes} paletes.`);
        }
    }
    console.log("[WPP] ===============================================");
    console.log("[WPP] Cruzamento de dados finalizado com SUCESSO!");
    console.log("[WPP] ===============================================");
}


// ==========================================
// ROTINA DE BACKUP AUTOMATICO
// ==========================================
const cron = require('node-cron');
const { executarBackupDiario } = require('./backup.js');

// Agenda o backup para rodar todos os dias as 23:50 (Horario de Brasilia)
cron.schedule('50 23 * * *', () => {
    executarBackupDiario();
}, { timezone: "America/Sao_Paulo" });
