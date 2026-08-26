const { createClient } = require('@supabase/supabase-js');
const ExcelJS = require('exceljs');
const nodemailer = require('nodemailer');
const fs = require('fs');
require('dotenv').config({ path: '../.env' });

const SUPABASE_URL = process.env.SUPABASE_URL || "https://zkqzejnflpzknuuirlav.supabase.co";
const SUPABASE_KEY = process.env.SUPABASE_KEY || "sb_publishable_8pSOHjRSllI9wWVYPkmYFA_AfzxV-QS";
const supabase = createClient(SUPABASE_URL, SUPABASE_KEY);

async function executarBackupDiario() {
    console.log("[BACKUP] Iniciando rotina de backup noturno...");
    try {
        const { data, error } = await supabase.from('deliveries').select('*');
        if (error) throw error;
        
        const workbook = new ExcelJS.Workbook();
        const worksheet = workbook.addWorksheet('Relatorio CHEP');
        
        worksheet.columns = [
            { header: 'Data', key: 'data', width: 15 },
            { header: 'Motorista', key: 'motorista', width: 25 },
            { header: 'Delivery', key: 'delivery', width: 20 },
            { header: 'Cliente', key: 'cliente', width: 30 },
            { header: 'Paletes', key: 'paletes', width: 15 },
            { header: 'P. Coletados', key: 'paletes_coletado', width: 15 },
            { header: 'Valor', key: 'valor', width: 15 },
            { header: 'H_Local', key: 'h_local', width: 15 },
            { header: 'H_Coletado', key: 'h_coletado', width: 15 },
            { header: 'H_Finalizado', key: 'h_finalizado', width: 15 },
            { header: 'Data Fechamento', key: 'df', width: 15 },
            { header: 'Status Operacional', key: 'status', width: 20 },
            { header: 'Status CHEP', key: 'status_chep', width: 20 },
            { header: 'SR', key: 'sr', width: 15 },
            { header: 'Motivo', key: 'motivo', width: 25 }
        ];
        
        // Order by date descending
        data.sort((a, b) => {
            const parseDate = (d) => {
                if (!d) return 0;
                const parts = d.split('/');
                if (parts.length === 3) {
                    return new Date(`${parts[2]}-${parts[1]}-${parts[0]}T00:00:00`).getTime();
                }
                return 0;
            };
            return parseDate(b.data) - parseDate(a.data);
        });
        
        data.forEach(row => {
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

            worksheet.addRow({
                data: row.data || '-',
                motorista: row.motorista || '-',
                delivery: row.delivery || '-',
                cliente: row.cliente || '-',
                paletes: (row.paletes !== null && row.paletes !== undefined) ? row.paletes : '-',
                paletes_coletado: (row.pc !== null && row.pc !== undefined) ? row.pc : '-',
                valor: row.valor || row.valor_frete || row.valor_total || '-',
                h_local: row.l_horario || '-',
                h_coletado: row.c_horario || '-',
                h_finalizado: row.f_horario || '-',
                df: row.df || row.data_finalizacao || '-',
                status: computedStatus,
                status_chep: row.status_chep || '-',
                sr: row.sr || '-',
                motivo: row.motivo || row.observacao || row.observacoes || '-'
            });
        });
        
        const hoje = new Date();
        const nomeArquivo = `Backup_CHEP_${hoje.getDate()}_${hoje.getMonth()+1}_${hoje.getFullYear()}.xlsx`;
        const filePath = `./${nomeArquivo}`;
        await workbook.xlsx.writeFile(filePath);
        
        console.log(`[BACKUP] Planilha gerada com sucesso: ${filePath}`);
        
        const emailUser = process.env.EMAIL_USER;
        const emailPass = process.env.EMAIL_PASS;
        
        if (!emailUser || !emailPass) {
            console.log("[BACKUP] Email ou Senha não configurados no .env! O arquivo Excel foi gerado no servidor, mas NÃO foi enviado para o Gmail.");
            return;
        }
        
        const transporter = nodemailer.createTransport({
            service: 'gmail',
            auth: {
                user: emailUser,
                pass: emailPass
            }
        });
        
        const mailOptions = {
            from: emailUser,
            to: 'gabrielpxt98@gmail.com',
            subject: `Backup Diário de Operações (CHEP) - ${hoje.toLocaleDateString('pt-BR')}`,
            text: 'Olá Gabriel,\n\nSegue em anexo a planilha com o backup de todas as entregas registradas no seu sistema até o momento.\n\nAtenciosamente,\nSeu Robô Gerente 🤖',
            attachments: [
                {
                    filename: nomeArquivo,
                    path: filePath
                }
            ]
        };
        
        await transporter.sendMail(mailOptions);
        console.log("[BACKUP] Email enviado com sucesso para gabrielpxt98@gmail.com!");
        
        // Apaga do servidor pra não lotar
        fs.unlinkSync(filePath);
        
    } catch(err) {
        console.error("[BACKUP] Erro no backup:", err.message);
    }
}

module.exports = { executarBackupDiario };
