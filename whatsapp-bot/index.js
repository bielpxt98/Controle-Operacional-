require('dotenv').config();
const { default: makeWASocket, useMultiFileAuthState, DisconnectReason, downloadMediaMessage } = require('@whiskeysockets/baileys');
const pino = require('pino');
const express = require('express');
const qrcode = require('qrcode');
const { GoogleGenerativeAI } = require('@google/generative-ai');
const { createClient } = require('@supabase/supabase-js');

const app = express();
const port = process.env.PORT || 3000;

// Configurações
const TARGET_SENDER = "Dona Luciana"; // ou o numero de telefone 55XX999999999@s.whatsapp.net
const GEMINI_API_KEY = process.env.GEMINI_API_KEY;
const SUPABASE_URL = process.env.SUPABASE_URL || "https://zkqzejnflpzknuuirlav.supabase.co";
const SUPABASE_KEY = process.env.SUPABASE_KEY || "sb_publishable_8pSOHjRSllI9wWVYPkmYFA_AfzxV-QS";

const supabase = createClient(SUPABASE_URL, SUPABASE_KEY);
const genAI  = new GoogleGenerativeAI(GEMINI_API_KEY);

let qrCodeData = "";
let isConnected = false;

async function processImageWithGemini(buffer) {
    console.log("Enviando imagem para o Gemini Vision...");
    const model = genAI.getGenerativeModel({ model: "gemini-1.5-flash" });
    
    const prompt = `Analise esta imagem que contém uma escala de motoristas e clientes.
Retorne APENAS um JSON válido no formato de array de objetos.
Cada objeto deve ter:
- "motorista": O nome do motorista (ex: LUIZ, GABRIEL, WILSON, FABIO, VALDEMIR, JONES, ARGEMIRO)
- "cliente": O nome do cliente ou destino (ex: JDE CAFE, DISTRIBUIDORA SANTA CRUZ, ASSAI, WMS MAX ATACADO, CABRAL E SOUSA, YOKI)
Não inclua marcações markdown, apenas o JSON bruto.`;
    
    const imageParts = [
        {
            inlineData: {
                data: buffer.toString("base64"),
                mimeType: "image/jpeg"
            }
        }
    ];

    try {
        const result = await model.generateContent([prompt, ...imageParts]);
        const response = await result.response;
        let text = response.text();
        text = text.replace(/```json/g, "").replace(/```/g, "").trim();
        return JSON.parse(text);
    } catch (error) {
        console.error("Erro no Gemini:", error);
        return null;
    }
}

async function updateSupabase(extractedData) {
    console.log("Atualizando Supabase com os dados:", extractedData);
    
    // Pega a data de amanhã ou de hoje (conforme a regra de negócio)
    // Para simplificar, vamos buscar todas as coletas pendentes e tentar casar o cliente
    const { data: coletas, error } = await supabase
        .from('deliveries')
        .select('*')
        .order('id', { ascending: false })
        .limit(50); // pega as ultimas 50 para achar as de hoje/amanha

    if (error) {
        console.error("Erro ao buscar Supabase:", error);
        return;
    }

    for (let extraido of extractedData) {
        const clienteAlvo = extraido.cliente.toUpperCase();
        // Acha a melhor correspondência no banco
        let coletaMatch = coletas.find(c => {
            if(!c.cliente) return false;
            const clienteBanco = c.cliente.toUpperCase();
            // Lógica de similaridade simples
            const palavrasAlvo = clienteAlvo.split(' ');
            return palavrasAlvo.some(p => p.length > 3 && clienteBanco.inclues(p));
        });

        if (coletaMatch) {
            console.log(`Match encontrado: ${clienteAlvo} -> ${coletaMatch.cliente}. Motorista será: ${extraido.motorista}`);
            
            // Aqui precisaria mapear o nome exato do dropdown do site, ex: "LUIZ" -> "LUIS CARLOS"
            // Por enquanto vamos colocar o nome que veio da IA
            
            const { error: updateError } = await supabase
                .from('deliveries')
                .update({ motorista: extraido.motorista })
                .eq('id', coletaMatch.id);
                
            if (updateError) {
                console.error(`Erro ao atualizar ID ${coletaMatch.id}:`, updateError);
            } else {
                console.log(`[OK] Coleta ${coletaMatch.id} atualizada com motorista ${extraido.motorista}`);
            }
        } else {
            console.log(`Nenhuma coleta encontrada no banco para o cliente: ${clienteAlvo}`);
        }
    }
    
    // Gatilho para o robô da CHEP (Arquitetado mas sem funcionar ainda)
    console.log("\r\n[GATILHO] Aqui o sistema chamaria o robô da CHEP no PC local para preencher o portal!\r\n");
}

async function startWhatsApp() {
    const { state, saveCreds } = await useMultiFileAuthState('auth_info_baileys');
    
    const sock = makeWASocket({
        auth: state,
        printQRInTerminal: true,
        logger: pino({ level: "silent" })
    });

    sock.ev.on('connection.update', (update) => {
        const { connection, lastDisconnect, qr } = update;
        if (qr) {
            qrCodeData = qr;
        }
        if (connection === 'close') {
            const shouldReconnect = (lastDisconnect.error)?.output?.statusCode !== DisconnectReason.loggedOut;
            console.log('Conexão fechada. Reconectando...', shouldReconnect);
            if (shouldReconnect) startWhatsApp();
        } else if (connection === 'open') {
            console.log('[OK WhatsApp Conectado!');
            isConnected = true;
            qrCodeData = "";
        }
    });

    sock.ev.on('creds.update', saveCreds);

    sock.ev.on('messages.upsert', async (m) => {
        const msg = m.messages[0];
        if (!msg.message || msg.key.fromMe) return;

        const senderName = msg.pushName || "";
        console.log(`Mensagem recebida de: ${senderName}`);

        if (senderName !== TARGET_SENDER && !msg.key.remoteJid.includes("123456789")) {
            // return; // COMENTADO PARA TESTES locais
        }

        const messageType = Object.keys(msg.message)[0];
        if (messageType === 'imageMessage') {
            console.log("[CAMPOM] Imagem detectada!");
            try {
                const buffer = await downloadMediaMessage(msg, 'buffer', { }, { logger: pino({ level: "silent" }) });
                const extractedJSON = await processImageWithGemini(buffer);
                
                if (extractedJSON && Array.isArray(extractedJSON)) {
                    await updateSupabase(extractedJSON);
                } else {
                    console.log("Não foi possível extrair dados estruturados da imagem.");
                }
                
            } catch (err) {
                console.error("Erro ao baixar ou processar imagem:", err);
            }
        }
    });
}

app.get('/', async (req, res) => {
    if (isConnected) {
        return res.send("<h1>WhatsApp Bot está Conectado! [OK]</h1><p>Aguardando mensagens da Dona Luciana...</p>");
    }
    if (qrCodeData) {
        try {
            const qrImage = await qrcode.toDataURL(qrCodeData);
            return res.send(`
                <h1>Conecte seu WhatsApp</h1>
                <p>Escaneie o QR Code abaixo com seu WhatsApp:</p>
                <img src="${qrImage}" alt="QR Code" />
                <p>A página recarregará automaticamente em 5 segundos...</p>
                <script>setTimeout(() => location.reload(), 5000);</script>
            `);
        } catch (err) {
            return res.send("Erro ao gerar QR Code");
        }
    }
    res.send("<h1>Iniciando WhatsApp... Recarregue em instantes.</h1>");
});

app.listen(port, () => {
    console.log(`Servidor rodando na porta ${port}`);
    startWhatsApp();
});
