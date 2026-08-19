const { chromium } = require('playwright');
const { createClient } = require('@supabase/supabase-js');
const fs = require('fs');
require('dotenv').config();

const supabase = createClient(
    process.env.SUPABASE_URL || "https://zkqzejnflpzknuuirlav.supabase.co",
    process.env.SUPABASE_KEY || "sb_publishable_8pSOHjRSllI9wWVYPkmYFA_AfzxV-QS"
);

async function runChepProgramacaoAmanha(deliveries) {
    if (!deliveries || deliveries.length === 0) return;
    console.log("[WEB] Iniciando Playwright (Node.js) portado do local...");

    const path = require('path');
    let bdMotoristas = {};
    try {
        const jsonPath = path.join(__dirname, 'motoristas.json');
        console.log("[WEB] Lendo motoristas de:", jsonPath);
        let jsonStr = fs.readFileSync(jsonPath, 'utf8');
        // Remove BOM invisível do Windows se existir
        if (jsonStr.charCodeAt(0) === 0xFEFF) {
            jsonStr = jsonStr.slice(1);
        }
        bdMotoristas = JSON.parse(jsonStr);
        console.log("[WEB] Motoristas carregados com sucesso!");
    } catch(e) { 
        console.error("[WEB] ERRO GRAVE ao ler motoristas.json:", e); 
    }

    const dadosExtraidos = [];
    for (const d of deliveries) {
        let nomeLimpo = (d.motorista || "").replace('▼', '').trim().toUpperCase();
        const primNome = nomeLimpo.split(' ')[0];
        let dMotorista = bdMotoristas[nomeLimpo] || bdMotoristas[primNome] || {};
        
        dadosExtraidos.push({
            id_banco: d.id, // para podermos atualizar no supabase depois
            id_delivery: String(d.delivery).trim(),
            nome: nomeLimpo,
            cpf: dMotorista.cpf || "",
            placa_cavalo: (dMotorista.placa || "").includes('/') ? dMotorista.placa.split('/')[0].trim() : (dMotorista.placa || dMotorista.placa_cavalo || ""),
            placa_reboque: (dMotorista.placa || "").includes('/') ? dMotorista.placa.split('/')[1].trim() : (dMotorista.placa_reboque || "")
        });
    }

    const browser = await chromium.launch({ headless: true, slowMo: 50 });
    const context = await browser.newContext({ viewport: { width: 1366, height: 768 } });
    const page = await context.newPage();

    console.log("[WEB] Acessando CHEP...");
    try {
        await page.goto("https://chep-aztms-pr1.jdadelivers.com/tm/framework/Frame.jsp", { timeout: 30000 });
        await page.waitForTimeout(3000);
    } catch (e) {}

    try {
        const targetFrame = page.frame('results');
        if (targetFrame) {
            console.log("[WEB] Preenchendo login...");
            const userInput = targetFrame.locator('input[type="text"].inputField:visible').first();
            const passInput = targetFrame.locator('input#dspLoginPassword:visible').first();

            await userInput.waitFor({ state: 'visible', timeout: 10000 });
            await passInput.waitFor({ state: 'visible', timeout: 10000 });

            await userInput.focus();
            await userInput.fill('210256_2');
            await passInput.focus();
            await passInput.fill('560221');

            const submitBtn = targetFrame.locator('a img[src*="login"], a:has-text("Login"), input[type="submit"], button:visible').first();
            if (await submitBtn.isVisible()) {
                await submitBtn.click();
            } else {
                await passInput.press('Enter');
            }

            console.log("[WEB] Logou! Aguardando menu...");

            let sbLink = null;
            for (let i = 0; i < 15; i++) {
                for (const f of page.frames()) {
                    const loc = f.locator('a:has-text("Transportation Smartbench")').first();
                    if (await loc.count() > 0 && await loc.isVisible()) {
                        sbLink = loc;
                        break;
                    }
                }
                if (sbLink) break;
                await page.waitForTimeout(2000);
            }

            let targetPage = page;
            if (sbLink) {
                console.log("[WEB] Clicando em Smartbench...");
                try {
                    const [newPage] = await Promise.all([
                        context.waitForEvent('page', { timeout: 5000 }),
                        sbLink.click()
                    ]);
                    targetPage = newPage;
                } catch(e) {
                    try { await sbLink.click(); } catch(err){}
                }

                console.log("[WEB] Aguardando Smartbench...");
                let progAmanha = null;
                for (let i = 0; i < 15; i++) {
                    for (const f of targetPage.frames()) {
                        const loc = f.locator('td:has-text("PROGRAMAÇÃO AMANHÃ")').first();
                        if (await loc.count() > 0 && await loc.isVisible()) {
                            progAmanha = loc;
                            break;
                        }
                    }
                    if (progAmanha) break;
                    await targetPage.waitForTimeout(2000);
                }

                if (progAmanha) {
                    console.log("[WEB] Clicando PROGRAMAÇÃO AMANHÃ...");
                    await progAmanha.click();
                    await targetPage.waitForTimeout(1000);
                    await progAmanha.dblclick();

                    console.log("[WEB] Aguardando tabela...");
                    let resultsFrame = null;
                    for (let i = 0; i < 15; i++) {
                        for (const f of targetPage.frames()) {
                            if (await f.locator('table.listTable').count() > 0 || await f.locator('text="ID da carga"').count() > 0) {
                                resultsFrame = f;
                                break;
                            }
                        }
                        if (resultsFrame) break;
                        await targetPage.waitForTimeout(1000);
                    }

                    if (resultsFrame) {
                        await targetPage.waitForTimeout(500);
                        
                        let colMap = { nome: 3, cpf: 4, placa_cavalo: 5, placa_reboque: -1 };
                        try {
                            const headers = await resultsFrame.locator('table.listTable').first().locator('thead th').allTextContents();
                            headers.forEach((h, i) => {
                                const hClean = h.trim().toLowerCase();
                                if (hClean.includes('do reboque') && !hClean.includes('placa')) colMap.nome = i;
                                else if (hClean.includes('carteira de habilita') || hClean.includes('cpf')) colMap.cpf = i;
                                else if (hClean.includes('ativo') || hClean.includes('cavalo')) colMap.placa_cavalo = i;
                                else if (hClean.includes('placa do reboque') || hClean.includes('da placa')) colMap.placa_reboque = i;
                            });
                            console.log("[WEB] Colunas:", colMap);
                        } catch(e) {}

                        let sucessos = [];

                        for (const d of dadosExtraidos) {
                            const termoBusca = d.id_delivery;
                            console.log(`[WEB] Procurando por: ${termoBusca}`);
                            
                            const rowsMatch = await resultsFrame.locator(`tr:has-text("${termoBusca}")`).all();
                            let row = null;
                            for (const r of rowsMatch) {
                                try {
                                    const col1Text = await r.locator(':scope > td').nth(1).innerText({ timeout: 500 });
                                    if (col1Text.trim().startsWith('4')) {
                                        row = r;
                                        break;
                                    }
                                } catch(e){}
                            }

                            if (row) {
                                console.log(`[WEB] -> Encontrou a linha para ${termoBusca}! Verificando...`);
                                
                                let precisaPreencher = false;
                                const campos = [
                                    { k: 'nome', col: colMap.nome },
                                    { k: 'cpf', col: colMap.cpf },
                                    { k: 'placa_cavalo', col: colMap.placa_cavalo }
                                ];
                                if (colMap.placa_reboque !== -1) campos.push({ k: 'placa_reboque', col: colMap.placa_reboque });

                                for (const c of campos) {
                                    if (d[c.k]) {
                                        try {
                                            const txtAtual = await row.locator(':scope > td').nth(c.col).innerText({ timeout: 1000 });
                                            if (!txtAtual.trim()) {
                                                precisaPreencher = true;
                                                break;
                                            }
                                        } catch(e) {}
                                    }
                                }

                                if (!precisaPreencher) {
                                    console.log(`[WEB] -> A coleta ${termoBusca} ja esta preenchida. Pulando digitacao.`);
                                    sucessos.push(d.id_banco);
                                } else {
                                    for (const c of campos) {
                                        if (d[c.k]) {
                                            const cell = row.locator(':scope > td').nth(c.col);
                                            await cell.scrollIntoViewIfNeeded();
                                            await cell.dblclick();
                                            await targetPage.waitForTimeout(100);
                                            await targetPage.keyboard.type(d[c.k]);
                                            await targetPage.waitForTimeout(50);
                                            await targetPage.keyboard.press('Enter');
                                        }
                                    }
                                    console.log(`[WEB] -> Sucesso! Dados preenchidos para ${termoBusca}.`);
                                    sucessos.push(d.id_banco);
                                    await targetPage.waitForTimeout(1000);
                                }
                            } else {
                                console.log(`[WEB] -> AVISO: Nao achou a linha para '${termoBusca}'.`);
                            }
                        }

                        
                        // LOGICA DE CASCATAS
                        let coletasPendentes = dadosExtraidos.filter(d => !sucessos.includes(d.id_banco));
                        if (coletasPendentes.length > 0) {
                            console.log(`[WEB] Iniciando busca avancada (Cascata) para ${coletasPendentes.length} pendentes...`);
                            let cascatasProcessadas = new Set();

                            while (coletasPendentes.length > 0) {
                                let reiniciarCascata = false;
                                try {
                                    // Desmarca caixinhas
                                    const caixinhasAtivas = await resultsFrame.locator('input[type="checkbox"]:checked').all();
                                    for (const cx of caixinhasAtivas) {
                                        try { await cx.uncheck({ timeout: 1000 }); } catch(e){}
                                    }

                                    const linhas = await resultsFrame.locator('table.listTable tbody tr').all();
                                    for (let row of linhas) {
                                        if (coletasPendentes.length === 0) break;

                                        try {
                                            const idCarga = (await row.locator(':scope > td').nth(1).innerText({ timeout: 1000 })).trim();
                                            if (!idCarga.startsWith('4')) continue;

                                            const idFornecimento = (await row.locator(':scope > td').nth(2).innerText({ timeout: 1000 })).trim();
                                            const txtLinha = (await row.innerText({ timeout: 1000 }));

                                            if (cascatasProcessadas.has(idCarga)) continue;

                                            if (idCarga && !idFornecimento) {
                                                cascatasProcessadas.add(idCarga);
                                                console.log(`[WEB] Analisando Cascata (Carga: ${idCarga})...`);

                                                const checkbox = row.locator(':scope > td').nth(0);
                                                await checkbox.scrollIntoViewIfNeeded({ timeout: 1000 });
                                                await checkbox.click({ timeout: 1000 });
                                                await targetPage.waitForTimeout(1000);

                                                try {
                                                    const btnCascata = resultsFrame.locator('td.otherToolStripButton:has-text("Cascata")').first();
                                                    if (await btnCascata.isVisible({ timeout: 2000 })) {
                                                        await btnCascata.click({ timeout: 2000 });
                                                        await targetPage.waitForTimeout(1000);
                                                        const btnFornec = resultsFrame.locator('div[role="presentation"]:has-text("Fornecimentos")').first();
                                                        if (await btnFornec.isVisible({ timeout: 2000 })) {
                                                            await btnFornec.click({ timeout: 2000 });
                                                        }
                                                    }
                                                } catch(e) {
                                                    try { await row.locator('td').nth(1).locator('a').first().click({ timeout: 2000 }); } catch(e){}
                                                }

                                                await targetPage.waitForTimeout(3000);

                                                let resolvidosCascata = [];
                                                let houveEdicao = false;

                                                for (const pendente of coletasPendentes) {
                                                    const tBusca = pendente.id_delivery;
                                                    if (await resultsFrame.locator(`text="${tBusca}"`).count() > 0) {
                                                        console.log(`[WEB] -> Cascata MATCH! O ID ${tBusca} esta dentro.`);
                                                        
                                                        let precisaPreencher = false;
                                                        if (!houveEdicao) {
                                                            const campos = [
                                                                { k: 'nome', col: colMap.nome },
                                                                { k: 'cpf', col: colMap.cpf },
                                                                { k: 'placa_cavalo', col: colMap.placa_cavalo }
                                                            ];
                                                            if (colMap.placa_reboque !== -1) campos.push({ k: 'placa_reboque', col: colMap.placa_reboque });

                                                            for (const c of campos) {
                                                                if (pendente[c.k]) {
                                                                    try {
                                                                        const txtAtual = await row.locator(':scope > td').nth(c.col).innerText({ timeout: 1000 });
                                                                        if (!txtAtual.trim()) {
                                                                            precisaPreencher = true;
                                                                            break;
                                                                        }
                                                                    } catch(e) {}
                                                                }
                                                            }
                                                        }

                                                        if (precisaPreencher) {
                                                            console.log("[WEB] -> Preenchendo linha principal...");
                                                            const campos = [
                                                                { k: 'nome', col: colMap.nome },
                                                                { k: 'cpf', col: colMap.cpf },
                                                                { k: 'placa_cavalo', col: colMap.placa_cavalo }
                                                            ];
                                                            if (colMap.placa_reboque !== -1) campos.push({ k: 'placa_reboque', col: colMap.placa_reboque });

                                                            for (const c of campos) {
                                                                if (pendente[c.k]) {
                                                                    const cell = row.locator(':scope > td').nth(c.col);
                                                                    await cell.scrollIntoViewIfNeeded();
                                                                    await cell.dblclick();
                                                                    await targetPage.waitForTimeout(100);
                                                                    await targetPage.keyboard.type(pendente[c.k]);
                                                                    await targetPage.waitForTimeout(50);
                                                                    await targetPage.keyboard.press('Enter');
                                                                }
                                                            }
                                                            houveEdicao = true;
                                                        } else {
                                                            console.log("[WEB] -> A linha principal ja tem os dados.");
                                                        }

                                                        resolvidosCascata.push(pendente);
                                                        await targetPage.waitForTimeout(1500);
                                                    }
                                                }

                                                for (const r of resolvidosCascata) {
                                                    coletasPendentes = coletasPendentes.filter(p => p.id_banco !== r.id_banco);
                                                    sucessos.push(r.id_banco);
                                                }

                                                try { await checkbox.uncheck({ timeout: 1000 }); } 
                                                catch(e) { try { await checkbox.click({ timeout: 1000 }); } catch(err){} }
                                                await targetPage.waitForTimeout(1000);

                                                if (houveEdicao) {
                                                    console.log(`[WEB] Salvando edicoes da cascata ${idCarga}...`);
                                                    try {
                                                        const btnEnviar = resultsFrame.locator('td.otherToolStripButton:has-text("Enviar")').first();
                                                        if (await btnEnviar.isVisible({ timeout: 3000 })) {
                                                            await btnEnviar.click();
                                                            await targetPage.waitForTimeout(4000);
                                                            for (const f of targetPage.frames()) {
                                                                if (await f.locator('table.listTable').count() > 0 || await f.locator('text="ID da carga"').count() > 0) {
                                                                    resultsFrame = f;
                                                                    break;
                                                                }
                                                            }
                                                        }
                                                    } catch(e) {}
                                                    reiniciarCascata = true;
                                                    break;
                                                }
                                            }
                                        } catch (rowE) {
                                            const strErr = rowE.message || "";
                                            if (strErr.includes("Timeout") || strErr.toLowerCase().includes("stale") || strErr.includes("Target closed")) {
                                                console.log("[WEB] -> A pagina recarregou. Reiniciando a busca...");
                                                reiniciarCascata = true;
                                                break;
                                            }
                                        }
                                    }

                                    if (!reiniciarCascata) {
                                        console.log("[WEB] Varredura de cascatas concluida.");
                                        break;
                                    }
                                } catch(e) { break; }
                            }
                        }

                        // Clicar em Enviar

                        if (sucessos.length > 0) {
                            try {
                                const btnEnviar = resultsFrame.locator('td.otherToolStripButton:has-text("Enviar")').first();
                                if (await btnEnviar.isVisible({ timeout: 3000 })) {
                                    await btnEnviar.click();
                                    console.log("[WEB] Botao ENVIAR clicado!");
                                    await targetPage.waitForTimeout(4000);
                                }
                            } catch(e) {}

                            // Atualiza Supabase para não repetir no futuro!
                            console.log(`[WEB] Atualizando Supabase para ${sucessos.length} coletas com PREENCHIDO...`);
                            for (const sid of sucessos) {
                                await supabase.from('deliveries').update({ status_chep: 'PREENCHIDO' }).eq('id', sid);
                            }
                        }
                    }
                }
            }
        }
    } catch(e) { console.log("Erro Fatal:", e.message); }

    console.log("[WEB] Fim. Fechando em 5 seg...");
    await new Promise(r => setTimeout(r, 5000));
    await browser.close();
}

module.exports = { runChepProgramacaoAmanha };
