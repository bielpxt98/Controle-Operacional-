const { createClient } = require('@supabase/supabase-js');
const fs = require('fs');
require('dotenv').config({ path: '../.env' });

const SUPABASE_URL = process.env.SUPABASE_URL || "https://zkqzejnflpzknuuirlav.supabase.co";
const SUPABASE_KEY = process.env.SUPABASE_KEY || "sb_publishable_8pSOHjRSllI9wWVYPkmYFA_AfzxV-QS";
const GOOGLE_SHEETS_WEBHOOK_URL = process.env.GOOGLE_SHEETS_WEBHOOK_URL || "";

const supabase = createClient(SUPABASE_URL, SUPABASE_KEY);

async function sincronizarGoogleSheets(customUrl = null) {
    const url = customUrl || GOOGLE_SHEETS_WEBHOOK_URL;
    if (!url) {
        console.log("[GOOGLE-SHEETS] Nenhuma URL de Webhook configurada em GOOGLE_SHEETS_WEBHOOK_URL no .env");
        return { sucesso: false, erro: "URL_NAO_CONFIGURADA" };
    }

    console.log("[GOOGLE-SHEETS] Buscando coletas no Supabase para sincronização...");
    try {
        const { data, error } = await supabase.from('deliveries').select('*');
        if (error) throw error;

        // Ordenar por data decrescente
        data.sort((a, b) => {
            const parseDate = (d) => {
                if (!d) return 0;
                const parts = d.split(/[\/\-]/);
                if (parts.length === 3) {
                    let day = parts[0].padStart(2, '0');
                    let mon = parts[1].padStart(2, '0');
                    let yr = parts[2].length === 2 ? '20' + parts[2] : parts[2];
                    return new Date(`${yr}-${mon}-${day}T00:00:00`).getTime();
                }
                return 0;
            };
            return parseDate(b.data) - parseDate(a.data);
        });

        const rows = data.map(row => {
            let computedStatus = "PENDENTE";
            const pc = parseInt(row.pc);
            const hl = row.l_horario && row.l_horario.trim() !== '' && row.l_horario !== '-';
            const hc = row.c_horario && row.c_horario.trim() !== '' && row.c_horario !== '-';
            const hf = row.f_horario && row.f_horario.trim() !== '' && row.f_horario !== '-';
            const obs = (row.observacao || row.observacoes || row.motivo || "").toLowerCase();

            if (!isNaN(pc) && pc > 0 && hl && hc && hf) {
                computedStatus = "FINALIZADO";
            } else if ((isNaN(pc) || pc === 0) && hl && hf && obs.includes("bloqueio")) {
                computedStatus = "BLOQUEIO";
            } else if ((isNaN(pc) || pc === 0) && hl && hf && obs.includes("deslocamento")) {
                computedStatus = "DESLOCAMENTO";
            }

            return {
                data: row.data || '',
                motorista: row.motorista || '',
                delivery: row.delivery || '',
                cliente: row.cliente || '',
                paletes: (row.paletes !== null && row.paletes !== undefined) ? row.paletes : '',
                paletes_coletado: (row.pc !== null && row.pc !== undefined) ? row.pc : '',
                valor: row.valor || row.valor_frete || row.valor_total || '',
                h_local: row.l_horario || '',
                h_coletado: row.c_horario || '',
                h_finalizado: row.f_horario || '',
                df: row.df || row.data_finalizacao || '',
                status: computedStatus,
                status_chep: row.status_chep || '',
                sr: row.sr || '',
                motivo: row.motivo || row.observacao || row.observacoes || ''
            };
        });

        console.log(`[GOOGLE-SHEETS] Enviando ${rows.length} registros para a Planilha...`);

        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ coletas: rows })
        });

        const resText = await response.text();
        console.log("[GOOGLE-SHEETS] Resposta do Google:", resText);
        return { sucesso: true, registros: rows.length };
    } catch (err) {
        console.error("[GOOGLE-SHEETS] Erro ao sincronizar:", err.message);
        return { sucesso: false, erro: err.message };
    }
}

module.exports = { sincronizarGoogleSheets };
