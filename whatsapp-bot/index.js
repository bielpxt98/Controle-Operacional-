

// SILENCIADOR MÁXIMO DE LOGS DE CRIPTOGRAFIA
['log', 'info', 'warn', 'error', 'debug'].forEach(method => {
    const orig = console[method];
    console[method] = function(...args) {
        if (args.length > 0 && typeof args[0] === 'string') {
            const str = args[0];
            if (str.includes('SessionEntry') || str.includes('ephemeralKeyPair') || str.includes('closing session') || str.includes('closing open session') || str.includes('chainKey') || str.includes('messageKeys')) {
                return; // Ignora logs de criptografia do libsignal
            }
        }
        orig.apply(console, args);
    };
});

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
            
            if (!groupName.toLowerCase().includes("purm salvador") && !groupName.toLowerCase().includes("trabalho")) {
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
    const numE = "558193792908"; // Gabriel Peixoto antigo
    const numF = "557186888333"; // Gabriel Peixoto atual
    const isAdmin = msg.key.fromMe || remetenteNum.includes("557181942525") || remetenteNum.includes(numA) || remetenteNum.includes(numB) || remetenteNum.includes(numC) || remetenteNum.includes(numD) || remetenteNum.includes(numE) || remetenteNum.includes(numF) || senderName.toLowerCase().includes("luciana") || senderName.toLowerCase().includes("osvaldo");

    // =========================================================
    // 1. MENSAGEM NO PRIVADO
    // =========================================================
    if (!isFromGroup) {
        if (!isAdmin) return; 
        
        let json = null;
        if (msg.message.imageMessage) {
            console.log("[WPP-PRIVADO] Nova imagem de programacao de " + senderName);
            const { downloadMediaMessage } = require('@whiskeysockets/baileys');
            const pino = require('pino');
            const buffer = await downloadMediaMessage(msg, 'buffer', {}, { logger: pino({ level: "silent" }) });
            json = await classifyImage(buffer, captionMsg, isFromGroup, false);
        } else if (txtMsg && txtMsg.toUpperCase().includes("PROGRAMA")) {
            console.log("[WPP-PRIVADO] Novo texto de programacao de " + senderName);
            json = await classifyImage(null, txtMsg, isFromGroup, true);
        } else {
            return;
        }

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


    // ==========================================
    // LOGICA DE SR ENVIADA PELO ADMIN
    // ==========================================
    if (isAdmin && txtMsg.toUpperCase().includes('SR') && quotedMsg && quotedMsg.imageMessage) {
        const srMatch = txtMsg.match(/\b\d{8}\b/);
        if (srMatch) {
            const numeroSR = srMatch[0];
            const motoristasConhecidos = ["WILSON", "GABRIEL", "ARGEMIRO", "VALDEMIR", "JONES", "LUIS", "FABIO", "JEAN", "ARIEL"];
            let motoristaAlvo = motoristasConhecidos.find(m => txtMsg.toUpperCase().includes(m));
            
            if (motoristaAlvo) {
                console.log(`[WPP-ADMIN] Identificada SR ${numeroSR} para ${motoristaAlvo}`);
                
                // Buscar a coleta pendente desse motorista hoje
                let query = supabase.from('deliveries').select('id').ilike('motorista', `%${motoristaAlvo}%`).ilike('data', `%${dataHojeCurta}%`).is('f_horario', null).limit(1);
                const { data: pendentes } = await query;
                
                if (pendentes && pendentes.length > 0) {
                    const { error: updErr } = await supabase.from('deliveries').update({
                        sr: numeroSR,
                        f_horario: horaAtual,
                        status: 'CONCLUIDO',
                        data_finalizacao: dataHojeCurta
                    }).eq('id', pendentes[0].id);
                    
                    if (updErr) console.log('[ERRO SUPABASE SR]', updErr);
                    
                    await sock.sendMessage('120363408148934220@g.us', { text: `âœ… SR ${numeroSR} registrada para ${motoristaAlvo}! (H_FINALIZADO: ${horaAtual})` });
                    console.log(`[WPP-ADMIN] SR salva com sucesso.`);
                    return; // Interrompe para nao processar como delivery normal
                } else {
                    console.log(`[WPP-ADMIN] Nao achei coleta pendente para ${motoristaAlvo} hoje.`);
                }
            }
        }
    }

    // ==========================================
    // LÓGICA DE MARCAÇÃO MANUAL H_LOCAL (ADMIN)
    // ==========================================
    if (isAdmin && txtMsg) {
        const motoristasConhecidos = ["WILSON", "GABRIEL", "ARGEMIRO", "VALDEMIR", "JONES", "LUIZ", "LUIS", "FABIO", "JEAN", "ARIEL"];
        const palavrasMsg = txtMsg.trim().split(/\s+/);
        const firstWord = palavrasMsg[0].toUpperCase();
        
        if (motoristasConhecidos.includes(firstWord) && palavrasMsg.length >= 2 && !/^programa[cç][aã]o/i.test(txtMsg)) {
            const motoristaAlvo = firstWord;
            const dicaLocal = palavrasMsg.slice(1).join(" ").toLowerCase();
            
            console.log(`[WPP-ADMIN] Tentativa de marcação manual H_LOCAL para ${motoristaAlvo}. Dica: ${dicaLocal}`);
            
            const { data: pendentes } = await supabase.from('deliveries').select('id, cliente')
                .ilike('motorista', `%${motoristaAlvo}%`)
                .ilike('data', `%${dataHojeCurta}%`)
                .is('l_horario', null)
                .not('delivery', 'ilike', '340%');
                
            if (pendentes && pendentes.length > 0) {
                let escolhido = pendentes[0];
                let palavrasDica = dicaLocal.replace(/[^\w\s]/g, '').split(' ').filter(p => p.length >= 2);
                if (palavrasDica.length === 0) palavrasDica = [dicaLocal];
                
                let melhorPontuacao = -1;
                for (let p of pendentes) {
                    let nomeDB = (p.cliente || "").toLowerCase();
                    let pontuacao = 0;
                    for (let pd of palavrasDica) {
                        if (nomeDB.includes(pd)) pontuacao++;
                    }
                    if (pontuacao > melhorPontuacao) {
                        melhorPontuacao = pontuacao;
                        escolhido = p;
                    }
                }
                
                if (escolhido) {
                    await supabase.from('deliveries').update({ l_horario: horaAtual }).eq('id', escolhido.id);
                    await sock.sendMessage('120363408148934220@g.us', { text: `📍 H_LOCAL marcado manualmente para ${motoristaAlvo} (${horaAtual})\nCliente: ${escolhido.cliente || "N/A"}` });
                    console.log(`[WPP-ADMIN] H_LOCAL marcado no banco! (${horaAtual}) Cliente ID: ${escolhido.id}`);
                }
            } else {
                await sock.sendMessage('120363408148934220@g.us', { text: `❌ Não encontrei nenhuma coleta pendente hoje (sem H_LOCAL) para ${motoristaAlvo}.` });
            }
            return;
        }
    }

    // ==========================================
    // LÓGICA DE PROGRAMAÇÃO POR TEXTO (ADMIN)
    // ==========================================
    if (isAdmin && txtMsg.trim().toUpperCase().startsWith("PROGRAMA")) {
        console.log("[WPP-ADMIN] Detectou texto de programação no grupo!");
        const jsonText = await parseProgramacaoText(txtMsg);
        if (jsonText && jsonText.tipo === "PROGRAMACAO") {
            await handleMotorista(jsonText, senderName);
            await sock.sendMessage(msg.key.remoteJid, { text: `✅ Programação de cargas processada com sucesso via texto!` });
        }
        return;
    }

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
        if (!error) await sock.sendMessage('120363408148934220@g.us', { text: `📦 H_COLETADO marcado! Delivery: ${numeroDelivery} | Paletes: ${paletesNumStr}` });
        return;
    }

    const isLocation = !!msg.message.locationMessage || !!msg.message.liveLocationMessage;
    
    if (isLocation && !isAdmin) {
        console.log(`[WPP-GRUPO] H_LOCAL detectado para o motorista ${motoristaPrimeiroNome}`);
        
        const locName = (msg.message.locationMessage?.name || msg.message.locationMessage?.address || "").toLowerCase();
        
        const { data: pendentes } = await supabase.from('deliveries').select('id, cliente')
            .ilike('motorista', `%${motoristaPrimeiroNome}%`)
            .ilike('data', `%${dataHojeCurta}%`)
            .is('l_horario', null)
            .not('delivery', 'ilike', '340%')
            .order('id', { ascending: true });
            
        if (pendentes && pendentes.length === 1) {
            await supabase.from('deliveries').update({ l_horario: horaAtual }).eq('id', pendentes[0].id);
            await sock.sendMessage('120363408148934220@g.us', { text: `📍 H_LOCAL marcado para ${motoristaPrimeiroNome} (${horaAtual})\nCliente: ${pendentes[0].cliente || "N/A"}` });
            console.log(`[WPP-GRUPO] H_LOCAL marcado no banco! (${horaAtual})`);
        } else if (pendentes && pendentes.length > 1) {
            let escolhido = null;
            if (locName) {
                let palavrasDica = locName.replace(/[^\w\s]/g, '').split(' ').filter(p => p.length >= 3);
                let melhorPontuacao = 0;
                for (let p of pendentes) {
                    let nomeDB = (p.cliente || "").toLowerCase();
                    let pontuacao = 0;
                    for (let pd of palavrasDica) {
                        if (nomeDB.includes(pd)) pontuacao++;
                    }
                    if (pontuacao > melhorPontuacao && pontuacao > 0) {
                        melhorPontuacao = pontuacao;
                        escolhido = p;
                    }
                }
            }
            
            if (escolhido) {
                await supabase.from('deliveries').update({ l_horario: horaAtual }).eq('id', escolhido.id);
                await sock.sendMessage('120363408148934220@g.us', { text: `📍 H_LOCAL marcado para ${motoristaPrimeiroNome} (${horaAtual}) via GPS Inteligente!\nCliente: ${escolhido.cliente || "N/A"}` });
                console.log(`[WPP-GRUPO] H_LOCAL marcado no banco por GPS Inteligente! (${horaAtual})`);
            } else {
                let msgOpcoes = pendentes.map(p => `- ${p.cliente}`).join('\n');
                await sock.sendMessage('120363408148934220@g.us', { text: `⚠️ O motorista ${motoristaPrimeiroNome} enviou a localização, mas possui ${pendentes.length} coletas pendentes:\n\n${msgOpcoes}\n\n👉 Responda com o nome do motorista e o local (ex: "${motoristaPrimeiroNome} Cabula") para registrar a chegada.` });
                console.log(`[WPP-GRUPO] Aguardando desempate manual para ${motoristaPrimeiroNome}.`);
            }
        } else {
            console.log(`[WPP-GRUPO] FALHA: Nenhuma carga vazia (l_horario=null) achada para motorista=${motoristaPrimeiroNome} na data=${dataHojeCurta}`);
        }
        return;
    }

    if (msg.message.imageMessage && !deliveryMatch) {
        console.log(`[WPP-GRUPO] Foto enviada por ${motoristaPrimeiroNome}. Analisando se é NF Carimbada...`);
        const { downloadMediaMessage } = require('@whiskeysockets/baileys');
        const pino = require('pino');
        const buffer = await downloadMediaMessage(msg, 'buffer', {}, { logger: pino({ level: "silent" }) });
        const json = await classifyImage(buffer, captionMsg, isFromGroup);
        if (json && json.tipo === "NF_ASSINADA") {
            const clienteLimpo = (json.cliente || "").toUpperCase().trim();
            const deliveryLido = json.delivery || "";
            console.log(`[WPP-GRUPO] NF ASSINADA! Cliente: ${clienteLimpo} | Delivery: ${deliveryLido}`);
            
            // Estrategia 1: Buscar SOMENTE pelo numero de delivery (mais confiavel)
            // Extrai todas as sequencias de 10 digitos do que a IA leu (corrige OCR impreciso)
            const deliveryStr = String(deliveryLido || "");
            const candidatos10 = [];
            if (deliveryStr.length === 10) {
                candidatos10.push(deliveryStr);
            } else if (deliveryStr.length > 10) {
                // Tenta todas as janelas de 10 digitos dentro do numero lido
                for (let i = 0; i <= deliveryStr.length - 10; i++) {
                    const sub = deliveryStr.slice(i, i + 10);
                    if (/^\d{10}$/.test(sub)) candidatos10.push(sub);
                }
            }
            
            let finalizavelId = null;
            let finalizavelDelivery = deliveryLido;
            let finalizavelCliente = clienteLimpo;
            
            for (const num of candidatos10) {
                const { data: exato } = await supabase.from('deliveries').select('id, delivery, cliente').eq('delivery', num).limit(1);
                if (exato && exato.length > 0) {
                    finalizavelId = exato[0].id;
                    finalizavelDelivery = exato[0].delivery;
                    finalizavelCliente = exato[0].cliente || clienteLimpo;
                    console.log(`[WPP-GRUPO] ✅ Delivery encontrado pelo numero: ${num} | Cliente: ${finalizavelCliente}`);
                    break;
                }
            }
            // Estrategia 2 (Fallback Inteligente): Busca pelas cargas do motorista e cruza com o NOME DO CLIENTE lido
            if (!finalizavelId) {
                console.log(`[WPP-GRUPO] Delivery não encontrado. Tentando FALLBACK INTELIGENTE cruzando cliente para motorista=${motoristaPrimeiroNome}...`);
                
                // Busca TODAS as coletas do motorista que ainda não foram concluídas (pode ser de dias anteriores)
                const { data: pendentes } = await supabase.from('deliveries')
                    .select('id, delivery, cliente, f_horario, data')
                    .ilike('motorista', `%${motoristaPrimeiroNome}%`)
                    .neq('status', 'CONCLUIDO')
                    .order('id', { ascending: true });

                if (pendentes && pendentes.length > 0) {
                    // Tenta achar uma coleta onde o nome do cliente bata com o que a IA leu
                    let alvo = null;
                    const clienteIA = clienteLimpo.split(' ')[0]; // Pega a primeira palavra (ex: "WMS" ou "ASSAI")
                    
                    for (const p of pendentes) {
                        if (p.cliente && p.cliente.toUpperCase().includes(clienteIA)) {
                            alvo = p;
                            console.log(`[WPP-GRUPO] Match de cliente encontrado no Fallback! Banco: ${p.cliente} | IA: ${clienteLimpo}`);
                            break;
                        }
                    }
                    
                    // Se achou pelo cliente, usa ela. Se não achou, NÃO preenche aleatório.
                    if (alvo) {
                        finalizavelId = alvo.id;
                        finalizavelDelivery = alvo.delivery || "N/A";
                        finalizavelCliente = alvo.cliente || "Desconhecido";
                        console.log(`[WPP-GRUPO] Fallback Inteligente definiu: ${finalizavelCliente} | Delivery: ${finalizavelDelivery}`);
                    }
                }
            }
            if (finalizavelId) {
                const { error: updErr } = await supabase.from('deliveries').update({ f_horario: horaAtual, status: 'CONCLUIDO', data_finalizacao: dataHojeCurta }).eq('id', finalizavelId);
                if (updErr) console.log('[ERRO SUPABASE]', updErr);
                await sock.sendMessage('120363408148934220@g.us', { text: `✅ H_FINALIZADO marcado! Cliente: ${finalizavelCliente} | Delivery: ${finalizavelDelivery} | Hora: ${horaAtual}` });
                console.log(`[WPP-GRUPO] H_FINALIZADO marcado com sucesso! ID: ${finalizavelId}`);
            } else {
                console.log(`[WPP-GRUPO] FALHA TOTAL: Nenhuma carga encontrada para motorista=${motoristaPrimeiroNome} hoje ou pelo delivery`);
                await sock.sendMessage('120363408148934220@g.us', { text: `⚠️ Não consegui localizar a coleta de ${motoristaPrimeiroNome} para finalizar.\nDelivery lido: ${deliveryLido}\nPreencha manualmente no painel.` });
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
            const diaHoje = hoje.getDate().toString().padStart(2, '0');
            const mesAtualStr = (hoje.getMonth() + 1).toString().padStart(2, '0');
            const dataHoje = diaHoje + '/' + mesAtualStr;
            
            const amanha = new Date();
            amanha.setDate(amanha.getDate() + 1);
            const diaAmanha = amanha.getDate().toString().padStart(2, '0');
            const mesAmanha = (amanha.getMonth() + 1).toString().padStart(2, '0');
            const dataAmanha = diaAmanha + '/' + mesAmanha; // Ex: 01/09
            
            const { data, error } = await supabase
                .from('deliveries')
                .select('*')
                .or(`data.ilike.%${dataHoje}%,data.ilike.%${dataAmanha}%`)
                .not('motorista', 'is', null)
                .not('motorista', 'ilike', '%SELECIONE%')
                .is('status_chep', null);
            
            if (error) { console.error("Erro banco:", error); }
            else if (data && data.length > 0) {
                console.log(`[CHEP-LOOP] Achei ${data.length} entregas! Iniciando Robô CHEP...`);
                await runChepProgramacaoAmanha(data);
            } else {
                console.log("[CHEP-LOOP] Nada pendente para hoje ou amanha.");
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
              const diaHoje = hoje.getDate().toString().padStart(2, '0');
              const mesAtualStr = (hoje.getMonth() + 1).toString().padStart(2, '0');
              const dataHoje = diaHoje + '/' + mesAtualStr;

              const amanha = new Date();
              amanha.setDate(amanha.getDate() + 1);
              const diaAmanha = amanha.getDate().toString().padStart(2, '0');
              const mesAmanha = (amanha.getMonth() + 1).toString().padStart(2, '0');
              const dataAmanha = diaAmanha + '/' + mesAmanha;
              
              const { data } = await supabase.from('deliveries').select('*').or(`data.ilike.%${dataHoje}%,data.ilike.%${dataAmanha}%`).not('motorista', 'is', null).not('motorista', 'ilike', '%SELECIONE%').is('status_chep', null);
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

async function classifyImage(buffer, textCaption, isFromGroup, isTextOnly = false) {
    try {
        console.log("[GEMINI] Analisando dados recebidos...");
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
            prompt = `Analise a programação de cargas diárias enviada pelo usuário (pode ser uma imagem de tabela ou texto corrido como 'ArgemiroWMS Max').
Extraia os dados em formato JSON estrito, sem formatação markdown.
Regras:
1. Identifique TODOS os motoristas listados e suas respectivas entregas. Mesmo que o texto esteja grudado sem espaços (ex: "JonesAssaí" ou "Luiz RemessaJDE"), separe o nome do motorista do nome do cliente/destino!
2. Extraia o NOME DO MOTORISTA (apenas o primeiro nome ou nome principal).
3. Na coluna/texto de destino, extraia o NOME PRINCIPAL E A LOCALIDADE/FILIAL para diferenciar lojas da mesma rede (Ex: "ASSAI PAU DA LIMA", "ASSAI ROTULA", "WMS MAX"). Se houver filiais, NÃO extraia só a primeira palavra!
4. Extraia também a quantidade de paletes ou caixas (um número).
5. Devolva no seguinte formato JSON: {"tipo": "PROGRAMACAO", "entregas": [{"motorista": "NOME DO MOTORISTA", "primeiro_nome_cliente": "PRIMEIRA_PALAVRA_CLIENTE", "paletes": 476}, ...]}
6. É CRUCIAL que você coloque TODAS as entregas identificadas no array "entregas". Não pule nenhuma!
7. Se não for sobre programação de entregas, devolva apenas: {"tipo": "IRRELEVANTE"}
Responda APENAS com o JSON.`;
        }

        let payload = [];
        if (isTextOnly) {
            payload = [{ text: prompt + '\n\nTexto enviado pelo usuário:\n' + textCaption }];
        } else {
            payload = [
                { text: prompt },
                {
                    inlineData: {
                        data: buffer.toString('base64'),
                        mimeType: 'image/jpeg'
                    }
                }
            ];
        }
        const keysToTry = [
            GEMINI_API_KEY,
            process.env.GEMINI_API_KEY_NEW || "",
            process.env.GEMINI_API_KEY_3 || ""
        ].filter(k => k && k.length > 10);
        
        const modelsToTry = [
            "gemini-3.5-flash",
            "gemini-3.7-flash",
            "gemini-3.5-flash-lite"
        ];

        let responseText = null;
        for (const apiKey of keysToTry) {
            const localGenAI = new (require('@google/generative-ai').GoogleGenerativeAI)(apiKey);
            let keyInvalid = false;
            for (const modelName of modelsToTry) {
                try {
                    console.log(`[GEMINI] Tentando ${modelName} na chave ...${apiKey.slice(-4)}...`);
                    const model = localGenAI.getGenerativeModel({ model: modelName });
                    
                    let timerId;
                    const timeoutPromise = new Promise((_, reject) => {
                        timerId = setTimeout(() => reject(new Error("Timeout de 90s atingido!")), 90000);
                    });
                    
                    const request = {
                        contents: [{ role: 'user', parts: payload }]
                    };
                    
                    const result = await Promise.race([
                        model.generateContent(request),
                        timeoutPromise
                    ]);
                    
                    clearTimeout(timerId);
                    responseText = result.response.text();
                    console.log(`[GEMINI] ✅ Resposta recebida do ${modelName}!`);
                    break;
                } catch (err) {
                    if (err.message.includes("429") || err.message.includes("RESOURCE_EXHAUSTED") || err.message.includes("quota")) {
                        console.error(`[GEMINI] ⚠️ COTA EXCEDIDA: ${modelName} / ...${apiKey.slice(-4)}`);
                    } else if (err.message.includes("API_KEY_INVALID") || err.message.includes("leaked") || err.message.includes("reported")) {
                        console.error(`[GEMINI] 🔑 CHAVE INVÁLIDA/BLOQUEADA: ...${apiKey.slice(-4)} — pulando esta chave`);
                        keyInvalid = true;
                        break;
                    } else if (err.message.includes("503") || err.message.includes("overloaded") || err.message.includes("UNAVAILABLE")) {
                        console.error(`[GEMINI] 🔴 SERVIDOR SOBRECARREGADO: ${modelName} / ...${apiKey.slice(-4)}`);
                    } else if (err.message.includes("Timeout")) {
                        console.error(`[GEMINI] ⏱️ TIMEOUT: ${modelName} / ...${apiKey.slice(-4)}`);
                    } else {
                        console.error(`[GEMINI] ❌ ERRO: ${modelName} / ...${apiKey.slice(-4)} | ${err.message.slice(0, 120)}`);
                    }
                }
            }
            if (keyInvalid) continue;
            if (responseText) break;
        }
        
        if (!responseText) {
            throw new Error("Todos os modelos da lista falharam por timeout ou cota de limite.");
        }
        
        let cleanJson = responseText.replace(/```json/g, '').replace(/```/g, '').trim();
        const json = JSON.parse(cleanJson);
        console.log("[GEMINI] Resultado:", JSON.stringify(json));
        return json;
    } catch(e) {
        console.log("[GEMINI] CAIU NO CATCH! Erro:", e.message);
        return { tipo: "IRRELEVANTE" };
    }
}

async function parseProgramacaoText(textoCompleto) {
    try {
        console.log("[GEMINI] Analisando texto de programação...");
        const prompt = `Você é um assistente que organiza escalas de trabalho. Analise o seguinte texto de programação de cargas e extraia os dados em formato JSON estrito, sem formatação markdown.
Texto recebido: """${textoCompleto}"""

Regras:
1. Extraia o NOME DO MOTORISTA (apenas o primeiro nome) para cada viagem.
2. Extraia o NOME PRINCIPAL E A LOCALIDADE/FILIAL para diferenciar lojas da mesma rede (Ex: "ASSAI PAU DA LIMA", "ASSAI ROTULA", "WMS MAX CABULA"). Não extraia só a primeira palavra, pegue a filial também!
3. Extraia também a quantidade de paletes ou caixas (um número). Se não houver, extraia 0.
4. Devolva EXATAMENTE no seguinte formato JSON (e NADA mais):
{"tipo": "PROGRAMACAO", "entregas": [{"motorista": "NOME DO MOTORISTA", "primeiro_nome_cliente": "CLIENTE_COM_FILIAL", "paletes": 476}]}
5. Coloque TODAS as entregas encontradas no array "entregas". Não pule nenhuma! Se não encontrar nenhuma, devolva {"tipo": "IRRELEVANTE"}.`;

        const keysToTry = [
            GEMINI_API_KEY,
            process.env.GEMINI_API_KEY_NEW || "",
            process.env.GEMINI_API_KEY_3 || ""
        ].filter(k => k && k.length > 10);
        
        const modelsToTry = [
            "gemini-3.5-flash",
            "gemini-3.7-flash",
            "gemini-3.5-flash-lite"
        ];

        let responseText = null;
        for (const apiKey of keysToTry) {
            const localGenAI = new (require('@google/generative-ai').GoogleGenerativeAI)(apiKey);
            let keyInvalid = false;
            for (const modelName of modelsToTry) {
                try {
                    console.log(`[GEMINI-TEXTO] Tentando ${modelName} na chave ...${apiKey.slice(-4)}...`);
                    const model = localGenAI.getGenerativeModel({ model: modelName });
                    
                    let timerId;
                    const timeoutPromise = new Promise((_, reject) => {
                        timerId = setTimeout(() => reject(new Error("Timeout de 60s atingido!")), 60000);
                    });
                    
                    const request = {
                        contents: [{ role: 'user', parts: [{ text: prompt }] }]
                    };
                    
                    const result = await Promise.race([
                        model.generateContent(request),
                        timeoutPromise
                    ]);
                    
                    clearTimeout(timerId);
                    responseText = result.response.text();
                    console.log(`[GEMINI-TEXTO] ✅ Resposta recebida do ${modelName}!`);
                    break;
                } catch (err) {
                    if (err.message.includes("429") || err.message.includes("RESOURCE_EXHAUSTED") || err.message.includes("quota")) {
                        console.error(`[GEMINI-TEXTO] ⚠️ COTA EXCEDIDA: ${modelName} / ...${apiKey.slice(-4)}`);
                    } else if (err.message.includes("API_KEY_INVALID") || err.message.includes("leaked") || err.message.includes("reported")) {
                        console.error(`[GEMINI-TEXTO] 🔑 CHAVE INVÁLIDA/BLOQUEADA: ...${apiKey.slice(-4)} — pulando`);
                        keyInvalid = true;
                        break;
                    } else if (err.message.includes("503") || err.message.includes("UNAVAILABLE")) {
                        console.error(`[GEMINI-TEXTO] 🔴 SERVIDOR SOBRECARREGADO: ${modelName} / ...${apiKey.slice(-4)}`);
                    } else {
                        console.error(`[GEMINI-TEXTO] ❌ ERRO: ${modelName} / ...${apiKey.slice(-4)} | ${err.message.slice(0, 120)}`);
                    }
                }
            }
            if (keyInvalid) continue;
            if (responseText) break;
        }
        
        if (!responseText) throw new Error("Todos os modelos de texto falharam.");
        
        let cleanJson = responseText.replace(/```json/g, '').replace(/```/g, '').trim();
        const json = JSON.parse(cleanJson);
        console.log("[GEMINI-TEXTO] Resultado:", JSON.stringify(json));
        return json;
    } catch(e) {
        console.log("[GEMINI-TEXTO] Erro no catch:", e.message);
        return { tipo: "IRRELEVANTE" };
    }
}

async function handleEscala(json) {}

async function handleMotorista(json, senderName) {
    if (!json.entregas || !Array.isArray(json.entregas)) return;
    
    console.log(`[WPP] Processando ${json.entregas.length} entregas identificadas pela IA...`);
    
    const hoje = new Date();
    const amanha = new Date();
    amanha.setDate(amanha.getDate() + 1);
    const diaAmanha = amanha.getDate().toString().padStart(2, '0');
    const mesAmanha = (amanha.getMonth() + 1).toString().padStart(2, '0');
    const dataAmanhaCurta = diaAmanha + '/' + mesAmanha; // Ex: 01/09
    
    for (const entrega of json.entregas) {
        if (!entrega.motorista || !entrega.primeiro_nome_cliente) continue;
        
        // Remove acentos para busca mais resiliente no banco
        const removeAcentos = str => str.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
        const clienteBusca = removeAcentos(String(entrega.primeiro_nome_cliente).toUpperCase().trim());
        
        let motoristaFormatado = removeAcentos(String(entrega.motorista).toUpperCase().trim());
        
        // Garante que o CHEP e o banco tenham o nome COMPLETO mesmo se a IA só mandou o primeiro nome
        const mapNomes = {
            "LUIZ": "LUIS CARLOS",
            "LUIS": "LUIS CARLOS",
            "VALDEMIR": "VALDEMIR DE JESUS",
            "JONES": "JONES ROSARIO",
            "ARGEMIRO": "ARGEMIRO BORGES",
            "FABIO": "FABIO SOUZA",
            "GABRIEL": "GABRIEL BORGES",
            "WILSON": "WILSON REIS",
            "JEAN": "JEAN CARLOS",
            "ARIEL": "ARIEL"
        };
        for (const key of Object.keys(mapNomes)) {
            if (motoristaFormatado.includes(key)) {
                motoristaFormatado = mapNomes[key];
                break;
            }
        }

        const paletes = Number(entrega.paletes) || 0;
        
        console.log(`[WPP] Buscando no banco: Cliente '${clienteBusca}' com ${paletes} paletes para o motorista ${motoristaFormatado}...`);
        
        const clienteBuscaSanitizado = clienteBusca.replace(/[-()]/g, ' ');
        const palavrasBusca = clienteBuscaSanitizado.split(' ').filter(p => p.length > 2);
        
        // Busca TODAS as entregas sem motorista (ou com '-- SELECIONE --') 
        // Não filtramos mais por data, para garantir que ache a coleta não importa que dia foi criada
        let query = supabase
            .from('deliveries')
            .select('*')
            .or("motorista.is.null,motorista.eq.,motorista.ilike.%SELECIONE%");
            
        if (paletes > 0) {
            query = query.eq('paletes', paletes);
        }
        
        const { data: resultadosBrutos, error } = await query;
        
        let encontrados = [];
        if (resultadosBrutos && resultadosBrutos.length > 0) {
            function levenshtein(a, b) {
                const matrix = [];
                for (let i = 0; i <= b.length; i++) matrix[i] = [i];
                for (let j = 0; j <= a.length; j++) matrix[0][j] = j;
                for (let i = 1; i <= b.length; i++) {
                    for (let j = 1; j <= a.length; j++) {
                        if (b.charAt(i - 1) === a.charAt(j - 1)) matrix[i][j] = matrix[i - 1][j - 1];
                        else matrix[i][j] = Math.min(matrix[i - 1][j - 1] + 1, Math.min(matrix[i][j - 1] + 1, matrix[i - 1][j] + 1));
                    }
                }
                return matrix[b.length][a.length];
            }

            const resultadosComScore = resultadosBrutos.map(linha => {
                const clienteDB = String(linha.cliente || "").toUpperCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/[-()]/g, ' ');
                const palavrasDB = clienteDB.split(' ').filter(p => p.length > 2);
                
                let score = 0;
                for (const palavra of palavrasBusca) {
                    const achou = palavrasDB.some(pdb => {
                        if (pdb === palavra) return true;
                        if (pdb.includes(palavra) || palavra.includes(pdb)) return true;
                        if (palavra.length > 3 && levenshtein(palavra, pdb) <= 1) return true;
                        return false;
                    });
                    if (achou) score++;
                }
                return { ...linha, _score: score };
            }).filter(l => l._score > 0);
            
            // Ordena pelo maior score (mais palavras em comum)
            resultadosComScore.sort((a, b) => b._score - a._score);
            encontrados = resultadosComScore;
        }
            
        if (encontrados && encontrados.length > 0) {
             const alvo = encontrados[0];
             console.log(`[WPP] MATCH PERFEITO! Atribuindo Delivery ${alvo.delivery} ao motorista ${motoristaFormatado}...`);
             await supabase.from('deliveries').update({ motorista: motoristaFormatado }).eq('id', alvo.id);
        } else {
             console.log(`[WPP] AVISO: Nao encontrei entrega vazia compativel para o cliente '${clienteBusca}' com ${paletes} paletes.`);
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
