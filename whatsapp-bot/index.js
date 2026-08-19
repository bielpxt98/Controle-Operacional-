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
    console.log("[GEMINI] Analisando imagem da programacao...");
    const model = genAI.getGenerativeModel({ model: "gemini-1.5-flash" });
    const prompt = `Analise esta imagem da escala de motoristas. Legenda: ${textCaption}

Regras:
1. Extraia a DATA DA PROGRAMACAO mencionada na imagem ou na legenda (ex: '19.08.26', '19/08/2026'). Formate a data EXATAMENTE como DD/MM/AAAA (ex: 19/08/2026).
2. Extraia todas as linhas da tabela de escala, relacionando MOTORISTA, CLIENTE e PALETES.

Retorne APENAS um JSON bruto, sem markdown:
{
  "tipo": "ESCALA",
  "data_programacao": "DD/MM/AAAA",
  "dados_escala": [
    {"motorista": "LUIZ", "cliente": "JDE CAFE", "paletes": "476"}
  ]
}`;

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
    if (!json || json.tipo !== "ESCALA") return;
    
    console.log(`[ESCALA] Recebida programação para o dia: ${json.data_programacao}`);

    if (!json.dados_escala || json.dados_escala.length === 0) {
        return console.log("[LOGICA] Nenhum dado encontrado na escala.");
    }

    // Busca coletas APENAS da data extraída
    const { data: coletas, error } = await supabase
        .from('deliveries')
        .select('*')
        .eq('data', json.data_programacao);

    if (error) return console.error("[SUPABASE] Erro:", error);
    
    if (!coletas || coletas.length === 0) {
        return console.log(`[LOGICA] Nenhuma coleta encontrada no banco para a data ${json.data_programacao}. Crie as coletas no site primeiro.`);
    }

    // Atualiza os dados
    for (let extraido of json.dados_escala) {
        // Encontra a coleta pelo nome do cliente (similaridade simples)
        let match = coletas.find(c => c.cliente && c.cliente.toUpperCase().split(' ').some(p => p.length > 3 && extraido.cliente.toUpperCase().includes(p)));
        
        if (match) {
            let updateData = {};
            // Só atualiza se estiver vazio, conforme o pedido: "preencher tudo que falta (caso ja tenha algum preenchido)"
            if (!match.motorista || match.motorista.trim() === "") {
                updateData.motorista = extraido.motorista;
            } else {
                // Se o usuario quiser que SUBSTITUA, ele removeria o if. Mas pelo texto "caso ja tenha algum preenchido", 
                // assumimos que queremos respeitar os que estao preenchidos ou que forçamos a atualizaçao?
                // Vou SOBRESCREVER o motorista porque o usuario disse "vou editar algumas do dia 19 e realizar o teste".
                // Ele quer que o robo PREENCHA o restante. 
                // Na verdade, se o site já tem, é melhor deixar ele atualizar se for para consertar?
                // "preencher tudo que falta (caso ja tenha algum preenchido)" -> preencher SOMENTE o que falta!
                if (!match.motorista) updateData.motorista = extraido.motorista;
            }

            // O mesmo para paletes
            if ((!match.paletes || match.paletes == 0) && extraido.paletes) {
                updateData.paletes = extraido.paletes;
            }

            if (Object.keys(updateData).length > 0) {
                await supabase.from('deliveries').update(updateData).eq('id', match.id);
                console.log(`✅ [ESCALA] Atualizado ${match.cliente} -> ${JSON.stringify(updateData)}`);
            } else {
                console.log(`ℹ️ [ESCALA] ${match.cliente} já estava totalmente preenchido.`);
            }
        } else {
            console.log(`❌ [ESCALA] Cliente ${extraido.cliente} não encontrado no banco para o dia ${json.data_programacao}`);
        }
    }
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
            console.log('[WPP] ✅ Conectado!');
        }
    });
    sock.ev.on('creds.update', saveCreds);

    sock.ev.on('messages.upsert', async (m) => {
        const msg = m.messages[0];
        if (!msg.message || msg.key.fromMe) return;

        const senderName = msg.pushName || "";
        
        // FILTRO: Aceitar apenas se o nome for Osvaldo purm (ignorando maiusculas/minusculas)
        if (!senderName.toLowerCase().includes("osvaldo purm")) {
            return;
        }

        const textCaption = msg.message.imageMessage?.caption || "";

        if (Object.keys(msg.message)[0] === 'imageMessage') {
            console.log(`[WPP] Imagem recebida de ${senderName}`);
            const buffer = await downloadMediaMessage(msg, 'buffer', {}, { logger: pino({ level: "silent" }) });
            const json = await processImageWithGemini(buffer, textCaption);
            if (json) await handleLogic(json, senderName);
        }
    });
}
startWhatsApp();
