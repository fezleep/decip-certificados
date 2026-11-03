# Inicialização Windows — desenho da correção

## Intenção

Tornar a inicialização local do DECIP idempotente e diagnóstica: uma segunda execução deve reutilizar a instância saudável, enquanto uma porta ocupada por outro serviço deve ser explicada sem encerrar processos.

## Metas e restrições

- Manter `127.0.0.1:8765`, Windows e Python 3.12.
- Preservar integralmente `data/decip.db`, `output/`, geração de PDFs, SMTP e interface.
- Manter o servidor em primeiro plano para que `Ctrl+C` encerre o processo Python.
- Nunca encerrar automaticamente o processo que ocupa a porta.
- Exibir PID, executável e linha de comando quando o Windows permitir a consulta.

## Abordagens consideradas

1. Fazer toda a detecção em Batch/PowerShell. Tem poucas peças, mas é difícil testar de forma determinística e mistura detecção HTTP, rede e mensagens no BAT.
2. Usar arquivo PID/lock. Identifica instâncias iniciadas pelo launcher, mas deixa locks obsoletos após falhas e não distingue com segurança uma porta reutilizada.
3. Manter o BAT fino e usar um módulo Python para sondagem HTTP e diagnóstico do listener. É testável, não adiciona dependências e confirma a identidade pela resposta do próprio servidor. Esta é a abordagem escolhida.

## Desenho

O aplicativo expõe um endpoint local de saúde/identidade sem dados pessoais. Antes de iniciar, o launcher Python consulta esse endpoint. Se reconhecer o DECIP, abre a URL e termina com sucesso; se houver outro listener, coleta metadados do PID por comandos nativos do Windows, imprime o diagnóstico e termina com erro; se a porta estiver livre, devolve ao BAT a decisão de iniciar. O BAT abre o navegador somente depois que o processo do servidor tiver sido criado e mantido em primeiro plano.

## Não metas

Não alterar persistência, certificados, e-mail, telas, porta, dependências ou criar encerramento remoto. Não matar processos nem implementar daemon em segundo plano.
