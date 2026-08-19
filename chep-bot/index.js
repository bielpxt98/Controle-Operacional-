const puppeteer = require('puppeteer');
const { createClient } = require('@supabase/supabase-js');
require('dotenv').config();

const SUPABASE_URL = process.env.SUPABASE_URL || "https://zkqzejnflpzknuuirlav.supabase.co";
const SUPABASE_KEY = process.env.SUPABASE_KEY || "sb_publishable_8pSOHjRSllI9wWVYPkmYFA_AfzxV-QS";
const supabase = createClient(SUPABASE_URL, SUPABASE_KEY);

const motoristas = require('./motoristas.json');

async function checkAndRun() {
    console.log("[CHEP-BOT] Checando Supabase por entregas pendentes para a CHEP...");
    
    // Pega a data de amanha no formato DD/MM/YYYY
    const amanha = new Date();
    amanha.setDate(amanha.getDate() + 1);
    const dataAmanhaStr = amanha.toLocaleDateString('pt-BR');

    // Busca entregas de amanha que tenham motorista, mas ainda nao foram pra CHEP
    const { data: pendentes, error } = await supabase
        .from('deliveries')
        .select('*')
        // .eq('data', dataAmanhaStr) // Pega as de amanha. (Ou sem filtro de data para pegar qualquer atrasada)
        .not('motorista', 'is', null)
        .is('status_chep', null);

    if (error) {
        console.error("[CHEP-BOT] Erro no Supabase:", error);
        return;
    }

    if (!pendentes || pendentes.length === 0) {
        console.log("[CHEP-BOT] Nada pendente.");
        return;
    }

    console.log(`[CHEP-BOT] Encontrei ${pendentes.length} entregas pendentes para preencher na CHEP! Iniciando navegador...`);

    const browser = await puppeteer.launch({
        headless: true,
        args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
        executablePath: process.env.PUPPETEER_EXECUTABLE_PATH || null
    });

    try {
        const page = await browser.newPage();
        await page.setViewport({ width: 1366, height: 768 });
        
        console.log("[CHEP-BOT] Acessando portal...");
        await page.goto("https://chep-aztms-pr1.jdadelivers.com/tm/framework/Frame.jsp", { waitUntil: 'networkidle2', timeout: 60000 });
        await page.waitForTimeout(3000);

        // Login
        const frameResults = page.frames().find(f => f.name() === 'results');
        if (frameResults) {
            console.log("[CHEP-BOT] Fazendo Login...");
            await frameResults.waitForSelector('input[type="text"].inputField', { visible: true });
            await frameResults.type('input[type="text"].inputField', '210256_2');
            await frameResults.type('input#dspLoginPassword', '560221');
            
            const submitBtn = await frameResults.$('a img[src*="login"], a:has-text("Login"), input[type="submit"], button');
            if (submitBtn) {
                await submitBtn.click();
            } else {
                await frameResults.keyboard.press('Enter');
            }
        }

        await page.waitForTimeout(10000); // Aguarda login

        // Clica em Smartbench
        const frameNav = page.frames().find(f => f.name() === 'nav');
        if (frameNav) {
            console.log("[CHEP-BOT] Clicando em Transportation Smartbench...");
            const sbLinks = await frameNav.$x(`//a[contains(text(), "Transportation Smartbench")]`);
            if (sbLinks.length > 0) {
                const newPagePromise = new Promise(x => browser.once('targetcreated', target => x(target.page())));
                await sbLinks[0].click();
                const newPage = await newPagePromise;
                if (newPage) {
                    await newPage.setViewport({ width: 1366, height: 768 });
                    await newPage.waitForTimeout(10000);
                    
                    // Busca PROGRAMACAO AMANHA
                    let progAmanha = null;
                    for (const f of newPage.frames()) {
                        const els = await f.$x(`//*[contains(text(), "PROGRAMAÇÃO AMANHÃ") or contains(text(), "PROGRAMAÇAO AMANHA")]`);
                        if (els.length > 0) {
                            progAmanha = els[0];
                            break;
                        }
                    }

                    if (progAmanha) {
                        console.log("[CHEP-BOT] Clicando em PROGRAMAÇÃO AMANHÃ...");
                        await progAmanha.click();
                        await newPage.waitForTimeout(15000); // Tabela demora a carregar
                        
                        let resultsFrame = newPage.frames().find(f => f.url().includes('lbp.jsp') || f.name() === 'results' || f.name() === 'list');
                        if (!resultsFrame) {
                            for (const f of newPage.frames()) {
                                const tables = await f.$$('table.listTable');
                                if (tables.length > 0) { resultsFrame = f; break; }
                            }
                        }

                        if (resultsFrame) {
                            console.log("[CHEP-BOT] Tabela encontrada! Vamos preencher as entregas pendentes...");
                            
                            for (const deliv of pendentes) {
                                // Tenta achar o motorista no Dicionario
                                const firstName = (deliv.motorista || "").split(' ')[0].toUpperCase();
                                let dictData = motoristas[firstName];
                                if (!dictData) {
                                    // Procura uma chave no JSON que esteja contida no nome (ex: VALDEMIR DE JESUS -> acha VALDEMIR)
                                    for (const key in motoristas) {
                                        if (deliv.motorista.toUpperCase().includes(key)) {
                                            dictData = motoristas[key];
                                            break;
                                        }
                                    }
                                }

                                if (!dictData) {
                                    console.log(`[CHEP-BOT] Motorista ${deliv.motorista} nao encontrado no Dicionario (motoristas.json). Pulando...`);
                                    continue;
                                }

                                // Localiza a linha pela Delivery (ID do Fornecimento)
                                console.log(`[CHEP-BOT] Buscando Delivery ${deliv.delivery} para o motorista ${firstName}...`);
                                const rowXpath = `//tr[td[contains(., "${deliv.delivery}")]]`;
                                const rows = await resultsFrame.$x(rowXpath);
                                
                                if (rows.length > 0) {
                                    const row = rows[0];
                                    const tds = await row.$$('td');
                                    
                                    // Supondo a ordem da sua imagem: 
                                    // 0: Checkbox
                                    // 1: ID da carga
                                    // 2: ID do fornecimento (Delivery)
                                    // 3: Número do reboque (Nome do Motorista)
                                    // 4: Número da carteira (CPF)
                                    // 5: Nome do ativo (Placa)

                                    // Preenche NOME (Index 3)
                                    if (tds.length > 3) {
                                        await tds[3].evaluate(el => el.scrollIntoView());
                                        await tds[3].click({ clickCount: 2 });
                                        await newPage.waitForTimeout(1000);
                                        const inputs = await resultsFrame.$$('input[type="text"]');
                                        if (inputs.length > 0) {
                                            const lastInput = inputs[inputs.length - 1];
                                            await lastInput.click({clickCount: 3});
                                            await lastInput.type(firstName);
                                            await newPage.keyboard.press('Enter');
                                            await newPage.waitForTimeout(1000);
                                        }
                                    }

                                    // Preenche CPF (Index 4)
                                    if (tds.length > 4) {
                                        await tds[4].evaluate(el => el.scrollIntoView());
                                        await tds[4].click({ clickCount: 2 });
                                        await newPage.waitForTimeout(1000);
                                        const inputs = await resultsFrame.$$('input[type="text"]');
                                        if (inputs.length > 0) {
                                            const lastInput = inputs[inputs.length - 1];
                                            await lastInput.click({clickCount: 3});
                                            await lastInput.type(dictData.cpf);
                                            await newPage.keyboard.press('Enter');
                                            await newPage.waitForTimeout(1000);
                                        }
                                    }

                                    // Preenche PLACA (Index 5)
                                    if (tds.length > 5) {
                                        await tds[5].evaluate(el => el.scrollIntoView());
                                        await tds[5].click({ clickCount: 2 });
                                        await newPage.waitForTimeout(1000);
                                        const inputs = await resultsFrame.$$('input[type="text"]');
                                        if (inputs.length > 0) {
                                            const lastInput = inputs[inputs.length - 1];
                                            await lastInput.click({clickCount: 3});
                                            await lastInput.type(dictData.placa);
                                            await newPage.keyboard.press('Enter');
                                            await newPage.waitForTimeout(1000);
                                        }
                                    }

                                    console.log(`[CHEP-BOT] Preenchido: ${deliv.delivery} -> ${firstName} / ${dictData.cpf} / ${dictData.placa}`);
                                    
                                    // Marca no Supabase que deu certo
                                    await supabase.from('deliveries').update({ status_chep: 'CONCLUIDO' }).eq('id', deliv.id);
                                } else {
                                    console.log(`[CHEP-BOT] Delivery ${deliv.delivery} nao achada na tabela PROGRAMAÇÃO AMANHÃ.`);
                                }
                            }
                            console.log("[CHEP-BOT] Tudo preenchido!");
                        }
                    }
                }
            }
        }

    } catch (e) {
        console.error("[CHEP-BOT] Erro durante a execucao:", e);
    } finally {
        await browser.close();
    }
}

// Loop infinito: Roda a cada 2 minutos
console.log("[CHEP-BOT] Servico iniciado! Checando a cada 2 minutos...");
checkAndRun();
setInterval(checkAndRun, 120000);
