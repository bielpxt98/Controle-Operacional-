// Agora o test_chep.js correto simula: "acabei de preencher a escala, aciona o CHEP"
const { runChepProgramacaoAmanha } = require('./chep.js');

process.env.TEST_MODE = "true"; // Chrome visivel

// Simula as entregas que o Supabase teria retornado
// Use deliveries REAIS que estao na tela PROGRAMACAO AMANHA do portal CHEP
const entregasSimuladas = [
    {
        id: 999,
        delivery: "3788462926",  // <-- Troque por um ID real da tela PROGRAMACAO AMANHA
        motorista: "LUIZ",
        data: "20/08/2026"
    }
];

async function test() {
    console.log("=== TESTE ISOLADO DO ROBO CHEP ===");
    console.log("Simulando que a escala chegou e vamos preencher PROGRAMACAO AMANHA...");
    await runChepProgramacaoAmanha(entregasSimuladas);
    console.log("=== FIM DO TESTE ===");
}

test();
