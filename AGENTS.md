# Regras do projeto

- Comunicar e escrever a interface em português brasileiro.
- Manter `web.py` (interface/API), `services/` (regras) e `repository.py` (SQLite) separados.
- O servidor deve escutar somente em `127.0.0.1`.
- A prévia deve chamar exatamente o mesmo gerador usado no salvamento e no anexo.
- Geração e envio são eventos separados. Nunca marcar como enviado ao gerar.
- Nunca enviar e-mail real em testes. Use `RecordingTransport` ou SMTP simulado.
- Nunca registrar senha, conteúdo sensível da planilha ou credencial em log/SQLite.
- Senhas SMTP pertencem ao cofre do sistema via `keyring`.
- Não alterar silenciosamente nomes próprios; preservar a grafia importada.
- Todo certificado tem código persistente e único, reservado em transação SQLite.
- Não prometer consulta pública de autenticidade enquanto ela não existir.
- Arte institucional deve vir de `assets/institutional/`; não inventar logo ou selo.
- Atualizar `docs/STATUS.md` quando uma entrega ou limitação mudar.

## Decisões

- Flask + JavaScript sem framework: interface local leve e portável para web.
- ReportLab: PDF vetorial, texto selecionável e página A4 paisagem.
- SQLite: participantes, lotes, certificados, gerações, envios e configurações.
- XLSX via openpyxl com mapeamento automático e manual de colunas.
- Credencial via Windows Credential Manager (keyring); os demais parâmetros ficam no SQLite.

