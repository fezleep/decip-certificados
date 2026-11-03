# Inicialização Windows Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fazer `iniciar.bat` reutilizar uma instância DECIP saudável e diagnosticar com segurança qualquer outro ocupante da porta 8766.

**Architecture:** Um módulo Python isolará sondagem HTTP, inspeção da porta e formatação do diagnóstico; o BAT apenas interpreta códigos de saída e mantém o servidor em primeiro plano. Uma rota de saúde identifica o DECIP sem acessar dados pessoais.

**Tech Stack:** Python 3.12, Flask, `unittest`, Batch e utilitários nativos do Windows.

**Spec:** `docs/superpowers/specs/2026-11-03-inicializacao-windows-design.md`

## Global Constraints

- Servidor somente em `127.0.0.1:8766`.
- Não tocar em `data/decip.db` nem em `output/`.
- Não encerrar processos automaticamente.
- Não adicionar dependências nem reinstalar `.venv`.
- Mensagens de terminal em português brasileiro.

## Review Focus

- Resposta HTTP de outro serviço: deve ser classificada como conflito, não como DECIP.
- Listener sem permissão para consultar metadados: diagnóstico deve continuar útil.
- Instância DECIP ainda inicializando: sondagem deve tolerar uma resposta transitória sem matar ou duplicar processos.
- Falha ao abrir navegador: não deve derrubar um servidor válido.
- Encerramento por `Ctrl+C`: o servidor deve continuar como processo em primeiro plano, sem filho Python destacado.

---

### Task 1: Identidade e diagnóstico do listener

**Files:**
- Create: `app/launcher.py`
- Modify: `app/web.py`
- Test: `tests/test_launcher.py`

**Interfaces:**
- Produces: `probe_instance(host: str, port: int) -> ProbeResult`, `describe_listener(port: int) -> str` e `GET /api/health`.

- [ ] Escrever testes falhos para porta livre, DECIP existente, serviço alheio e metadados indisponíveis.
- [ ] Executar `python -m unittest tests.test_launcher -v` e confirmar falhas pela ausência das interfaces.
- [ ] Implementar a sondagem e a rota sem dados pessoais.
- [ ] Reexecutar os testes e confirmar aprovação.

### Task 2: Orquestração idempotente do BAT

**Files:**
- Modify: `iniciar.bat`
- Test: `tests/test_launcher.py`

**Interfaces:**
- Consumes: os códigos de saída do CLI em `app.launcher` para iniciar, reutilizar ou bloquear.

- [ ] Escrever testes falhos executando o BAT em sandboxes para instância existente, conflito e falha de runtime.
- [ ] Implementar mensagens, abertura do navegador e preservação do servidor em primeiro plano.
- [ ] Validar inicialização normal, segunda execução e conflito com serviço controlado.

### Task 3: Documentação e verificação final

**Files:**
- Modify: `README.md`
- Modify: `docs/STATUS.md`

- [ ] Documentar o comportamento e as limitações de diagnóstico.
- [ ] Rodar a suíte completa com `.venv\\Scripts\\python.exe -m unittest discover -v`.
- [ ] Revisar `git diff`, `git status` e confirmar que banco, saídas e credenciais não estão incluídos.
- [ ] Fazer commit e push de `main` sem force push, se o ambiente Git permitir escrita.
