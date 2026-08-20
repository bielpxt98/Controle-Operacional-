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
            { header: 'Motorista', key: 'motorista', width: 25 },
            { header: 'Delivery', key: 'delivery', width: 20 },
            { header: 'Cliente', key: 'clientes', width: 30 },
            { header: 'Paletes', key: 'paletes', width: 15 },
            { header: 'Valor', key: 'valor', width: 15 },
            { header: 'Data', key: 'data', width: 15 },
            { header: 'Status Operacional', key: 'status', width: 20 },
            { header: 'Status CHEP', key: 'status_chep', width: 20 }
        ];
        
        data.forEach(row => {
            worksheet.addRow({
                motorista: row.motorista || '-',
                delivery: row.delivery || '-',
                clientes: row.clientes || '-',
                paletes: row.paletes || '-',
                valor: row.valor || '-',
                data: row.data || '-',
                status: row.status || '-',
                status_chep: row.status_chep || '-'
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
