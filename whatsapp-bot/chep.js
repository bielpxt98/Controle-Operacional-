const puppeteer = require('puppeteer');

async function updateChepOccurrence(delivery, tipo, valor) {
    if (!delivery || !tipo || !valor) return false;
    console.log(`[CHEP-BOT] Acordando Chrome para preencher Ocorrencia... Delivery: ${delivery} | Tipo: ${tipo} | Valor: ${valor}`);
    
    let browser = null;
    try {
        browser = await puppeteer.launch({
            headless: true,
            args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
            executablePath: process.env.PUPPETEER_EXECUTABLE_PATH || null
        });
        
        const page = await browser.newPage();
        await page.setViewport({ width: 1366, height: 768 });
        
        await page.goto("https://chep-aztms-pr1.jdadelivers.com/tm/framework/Frame.jsp", { waitUntil: 'networkidle2', timeout: 60000 });
        await page.waitForTimeout(3000);

        // Login
        const frameResults = page.frames().find(f => f.name() === 'results');
        if (frameResults) {
            await frameResults.waitForSelector('input[type="text"].inputField', { visible: true });
            await frameResults.type('input[type="text"].inputField', '210256_2');
            await frameResults.type('input#dspLoginPassword', '560221');
            const submitBtn = await frameResults.$('a img[src*="login"], a:has-text("Login"), input[type="submit"], button');
            if (submitBtn) await submitBtn.click();
            else await frameResults.keyboard.press('Enter');
        }

        await page.waitForTimeout(10000);

        // Acessa Smartbench
        const frameNav = page.frames().find(f => f.name() === 'nav');
        if (!frameNav) return false;

        const sbLinks = await frameNav.$x(`//a[contains(text(), "Transportation Smartbench")]`);
        if (sbLinks.length === 0) return false;

        const newPagePromise = new Promise(x => browser.once('targetcreated', target => x(target.page())));
        await sbLinks[0].click();
        const newPage = await newPagePromise;
        if (!newPage) return false;

        await newPage.setViewport({ width: 1366, height: 768 });
        await newPage.waitForTimeout(10000);

        // Clica em COLETAS HOJE ou COLETAS ONTEM dependendo se não achar na hoje. Mas o mais seguro é COLETAS HOJE.
        let coletadas = null;
        for (const f of newPage.frames()) {
            const els = await f.$x(`//*[contains(text(), "COLETAS HOJE") or contains(text(), "COLETAS")]`);
            if (els.length > 0) { coletadas = els[0]; break; }
        }

        if (coletadas) {
            await coletadas.click();
            await newPage.waitForTimeout(15000);
            
            let resultsFrame = newPage.frames().find(f => f.url().includes('lbp.jsp') || f.name() === 'results' || f.name() === 'list');
            if (!resultsFrame) {
                for (const f of newPage.frames()) {
                    const tables = await f.$$('table.listTable');
                    if (tables.length > 0) { resultsFrame = f; break; }
                }
            }

            if (resultsFrame) {
                // Localiza a linha pela Delivery
                const rowXpath = `//tr[td[contains(., "${delivery}")]]`;
                const rows = await resultsFrame.$x(rowXpath);
                
                if (rows.length > 0) {
                    const row = rows[0];
                    const tds = await row.$$('td');
                    // Supondo a ordem da sua imagem CHEP original de ocorrencias
                    // Precisamos mapear os indices corretos para Chegada, Coleta, Finalizado
                    // Index sugerido (exemplo generico - na implementacao real voce ajusta os indices das colunas):
                    // 12 = H_LOCAL
                    // 13 = H_COLETADO
                    // 14 = H_FINALIZADO
                    // 15 = P_COLETADOS
                    
                    let colIndex = -1;
                    if (tipo === 'CHEGADA') colIndex = 12; // Ajuste para a coluna real de H_LOCAL
                    if (tipo === 'NF_COLETA') colIndex = 13; // Ajuste para a coluna real de H_COLETADO
                    if (tipo === 'NF_FINALIZADA') colIndex = 14; // Ajuste para a coluna real de H_FINALIZADO
                    if (tipo === 'PALETES') colIndex = 15; // Ajuste para P_COLETADOS
                    
                    if (colIndex > -1 && tds.length > colIndex) {
                        await tds[colIndex].evaluate(el => el.scrollIntoView());
                        await tds[colIndex].click({ clickCount: 2 });
                        await newPage.waitForTimeout(1000);
                        const inputs = await resultsFrame.$$('input[type="text"]');
                        if (inputs.length > 0) {
                            const lastInput = inputs[inputs.length - 1];
                            await lastInput.click({clickCount: 3});
                            await lastInput.type(valor);
                            await newPage.keyboard.press('Enter');
                            await newPage.waitForTimeout(2000);
                            console.log(`[CHEP-BOT] Preenchido com Sucesso: Delivery ${delivery} -> ${tipo} = ${valor}`);
                            return true;
                        }
                    }
                } else {
                    console.log(`[CHEP-BOT] Delivery ${delivery} nao encontrada na tabela CHEP.`);
                }
            }
        }
        return false;
    } catch (e) {
        console.error("[CHEP-BOT] Erro:", e);
        return false;
    } finally {
        if (browser) {
            console.log("[CHEP-BOT] Fechando Chrome para liberar RAM...");
            await browser.close();
        }
    }
}

module.exports = { updateChepOccurrence };
