const puppeteer = require('puppeteer');
const motoristas = require('./motoristas.json');

async function runChepProgramacaoAmanha(pendentes) {
    console.log("[CHEP-BOT] Iniciando Chrome para PROGRAMACAO AMANHA...");
    let browser = null;

    try {
        browser = await puppeteer.launch({
            headless: process.env.TEST_MODE ? false : true,
            args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
            executablePath: process.env.PUPPETEER_EXECUTABLE_PATH || null
        });

        const page = await browser.newPage();
        await page.setViewport({ width: 1366, height: 768 });

        await page.goto("https://chep-aztms-pr1.jdadelivers.com/tm/framework/Frame.jsp", { waitUntil: 'networkidle2', timeout: 60000 });
        await page.waitForTimeout(3000);

        // LOGIN
        const frameResults = page.frames().find(f => f.name() === 'results');
        if (!frameResults) { console.log("[CHEP-BOT] Frame de login nao encontrado."); return; }

        console.log("[CHEP-BOT] Fazendo login...");
        await frameResults.waitForSelector('input[type="text"].inputField', { visible: true, timeout: 10000 });
        await frameResults.type('input[type="text"].inputField', '210256_2');
        await frameResults.type('input#dspLoginPassword', '560221');
        const submitBtn = await frameResults.$('a img[src*="login"], input[type="submit"]');
        if (submitBtn) await submitBtn.click();
        else await frameResults.keyboard.press('Enter');

        await page.waitForTimeout(10000);
        console.log("[CHEP-BOT] Login efetuado. Abrindo Transportation Smartbench...");

        // NAVEGA PARA SMARTBENCH
        const frameNav = page.frames().find(f => f.name() === 'nav');
        if (!frameNav) { console.log("[CHEP-BOT] Frame de navegacao nao encontrado."); return; }

        const sbLinks = await frameNav.$x('//a[contains(text(), "Transportation Smartbench")]');
        if (sbLinks.length === 0) { console.log("[CHEP-BOT] Link do Smartbench nao encontrado."); return; }

        const newPagePromise = new Promise(x => browser.once('targetcreated', t => x(t.page())));
        await sbLinks[0].click();
        const newPage = await newPagePromise;
        if (!newPage) { console.log("[CHEP-BOT] Nova aba nao abriu."); return; }
        await newPage.setViewport({ width: 1366, height: 768 });
        await newPage.waitForTimeout(10000);

        // CLICA EM PROGRAMACAO AMANHA
        let progAmanha = null;
        for (const f of newPage.frames()) {
            const els = await f.$x('//*[contains(text(), "PROGRAMA") and contains(text(), "AMANH")]');
            if (els.length > 0) { progAmanha = els[0]; break; }
        }
        if (!progAmanha) { console.log("[CHEP-BOT] Link PROGRAMACAO AMANHA nao encontrado."); return; }

        console.log("[CHEP-BOT] Clicando em PROGRAMACAO AMANHA...");
        await progAmanha.click();
        await newPage.waitForTimeout(15000);

        // ACHA O FRAME DA TABELA
        let resultsFrame = null;
        for (const f of newPage.frames()) {
            const tables = await f.$$('table.listTable, table tbody tr td');
            if (tables.length > 2) { resultsFrame = f; break; }
        }
        if (!resultsFrame) { console.log("[CHEP-BOT] Frame da tabela nao encontrado."); return; }
        console.log("[CHEP-BOT] Tabela encontrada! Preenchendo " + pendentes.length + " motoristas...");

        // PREENCHE CADA ENTREGA
        const { createClient } = require('@supabase/supabase-js');
        const supabase = createClient(
            process.env.SUPABASE_URL || "https://zkqzejnflpzknuuirlav.supabase.co",
            process.env.SUPABASE_KEY || "sb_publishable_8pSOHjRSllI9wWVYPkmYFA_AfzxV-QS"
        );

        for (const deliv of pendentes) {
            // Busca dados do motorista no dicionario
            let dictData = null;
            const nomeMotorista = (deliv.motorista || "").toUpperCase();
            for (const key in motoristas) {
                if (nomeMotorista.includes(key)) {
                    dictData = motoristas[key];
                    break;
                }
            }
            if (!dictData) {
                console.log("[CHEP-BOT] AVISO: Motorista '" + deliv.motorista + "' nao esta no motoristas.json. Pulando.");
                continue;
            }

            // Acha a linha pelo numero da Delivery (ID do fornecimento)
            const rowXpath = `//tr[td[contains(., "${deliv.delivery}")]]`;
            const rows = await resultsFrame.$x(rowXpath);

            if (rows.length === 0) {
                console.log("[CHEP-BOT] Delivery " + deliv.delivery + " nao encontrada na tabela PROGRAMACAO AMANHA.");
                continue;
            }

            const row = rows[0];
            const tds = await row.$$('td');

            // Segundo a foto do usuario:
            // Col 0: checkbox
            // Col 1: ID da carga (link)
            // Col 2: ID do fornecimento (Delivery)
            // Col 3: Numero(s) do reboque  <-- PLACA DO CAVALO
            // Col 4: Numero(s) da carteira <-- CPF DO MOTORISTA
            // Col 5: Nome(s) do ativo      <-- NOME DO MOTORISTA
            const colReboque = 3;  // Placa
            const colCarteira = 4; // CPF
            const colAtivo = 5;    // Nome

            const fillCell = async (colIdx, valor) => {
                if (tds.length > colIdx) {
                    await tds[colIdx].evaluate(el => el.scrollIntoView());
                    await tds[colIdx].click({ clickCount: 2 });
                    await newPage.waitForTimeout(1000);
                    const inputs = await resultsFrame.$$('input[type="text"]');
                    if (inputs.length > 0) {
                        const inp = inputs[inputs.length - 1];
                        await inp.click({ clickCount: 3 });
                        await inp.type(valor);
                        await newPage.keyboard.press('Enter');
                        await newPage.waitForTimeout(1500);
                    }
                }
            };

            await fillCell(colReboque, dictData.placa);
            await fillCell(colCarteira, dictData.cpf);
            await fillCell(colAtivo, deliv.motorista.split(' ')[0]);

            console.log("[CHEP-BOT] ✅ Preenchido: Delivery " + deliv.delivery + " -> " + deliv.motorista + " / " + dictData.cpf + " / " + dictData.placa);

            // Marca no Supabase como concluido para nao tentar de novo
            await supabase.from('deliveries').update({ status_chep: 'CONCLUIDO' }).eq('id', deliv.id);
        }

        console.log("[CHEP-BOT] Tudo preenchido com sucesso!");

    } catch(e) {
        console.error("[CHEP-BOT] Erro:", e.message);
    } finally {
        if (browser) {
            console.log("[CHEP-BOT] Fechando Chrome para liberar RAM.");
            await browser.close();
        }
    }
}

module.exports = { runChepProgramacaoAmanha };
