# Status da implementação — 03/11/2026

## Inicialização idempotente no Windows

- `iniciar.bat` agora diferencia porta livre, instância funcional do DECIP e
  outro serviço na porta 8765.
- Uma segunda execução abre a instância existente no navegador e termina com
  sucesso, sem criar outro processo Python.
- Outro serviço produz diagnóstico com PID, nome, executável e comando quando
  essas informações estiverem acessíveis. O inicializador nunca encerra o
  processo automaticamente.
- A identificação usa `GET /api/health`, que retorna somente nome do serviço e
  estado; não expõe cadastros, certificados, configurações ou credenciais. Uma
  instância anterior a essa rota também é reconhecida pelo título estático da
  página, sem consultar `/api/state`.
- O servidor continua em primeiro plano para que `Ctrl+C` encerre o processo,
  sem daemon ou filho Python destacado pelo inicializador.
- Testes automatizados cobrem inicialização normal, instância duplicada, porta
  ocupada por outro serviço, falha de runtime e diagnóstico do listener. O
  sandbox de validação bloqueia conexões de loopback, por isso as fronteiras de
  socket e consulta ao Windows são simuladas nos testes, mantendo a lógica e o
  BAT executados de verdade. A suíte completa terminou com **29/29 testes
  aprovados**.

## Confirmação do usuário sobre a falha de cadastro

- O usuário informou em 28/09/2026 que o problema de cadastro que motivou as
  correções foi resolvido em sua aplicação.
- Essa informação é uma confirmação do usuário, separada das verificações
  técnicas anteriores feitas por mim: a instância local na porta 8765 foi
  inspecionada, identificada como processo antigo, reiniciada com o código atual
  e `/api/state` foi conferido para conter `registrations`, `participants` e
  `batch`. Os testes de navegador que realizei usaram banco fictício isolado; não
  reproduziram novo cadastro no banco real.

## Demonstração e documentação para publicação

- README reorganizado com a instalação Windows conferida contra `instalar.bat` e
  `iniciar.bat`. Instalação em máquina limpa não foi declarada como testada.
- Capturas reais do Chrome em `docs/images/`, com três participantes fictícios
  e PDFs gerados em diretório temporário fora do repositório: participantes,
  atividade preenchida, prévia completa e resultado. Nenhum e-mail foi enviado.
- `.gitignore` cobre banco local, PDFs/arquivos de saída, ambientes virtuais,
  perfis do Chrome, logs, credenciais em `.env` e backups. As capturas aprovadas
  em `docs/images/` não são ignoradas.
- Antes da preparação desta publicação, a pasta local não continha metadados
  `.git`, commits ou remotos. Foi criado o repositório Git local na branch `main`
  com o commit inicial `a13eb3492616fb84af8310a68dce41acd9e4d6cb`.
- A conta autenticada informada pelo GitHub é `fezleep`; a listagem acessível e a
  busca por `decip-certificados` não retornaram um repositório correspondente.
  O `gh` não está instalado e a integração GitHub disponível não oferece a ação
  de criar repositório. Portanto, nenhum remoto foi criado e o push não ocorreu.
  A publicação fica pendente até existir o destino privado
  `fezleep/decip-certificados` ou estar disponível a operação de criação.

## Correção do erro `findIndex` ao cadastrar

- A exceção acontecia no manipulador de `#participant-form`, depois do retorno
  bem-sucedido de `POST /api/participants`. Nesse ponto o SQLite já havia
  confirmado o cadastro e o vínculo com o lote.
- O frontend tentava reconciliar a resposta com
  `state.registrations.findIndex(...)` e `state.participants.findIndex(...)`.
  O contrato do endpoint, porém, não devolvia `registrations`; em combinações
  de frontend/backend de versões diferentes uma das listas ficava `undefined`.
  Repetir o clique depois da exceção podia cadastrar a mesma pessoa novamente.
- Cadastro e edição agora devolvem sempre o estado canônico completo:
  `participant`, `registrations`, `participants` e `batch`. A interface valida
  esse contrato e substitui suas listas pela versão relida do SQLite, sem
  atualização parcial por `findIndex`.
- O botão de salvar fica desabilitado e mostra “Salvando participante…” enquanto
  a requisição está em andamento. Uma resposta incompleta não dispara nova
  tentativa automática; a mensagem orienta atualizar a página antes de tentar
  novamente, evitando duplicidade quando a gravação já ocorreu.
- Teste Chrome/CDP clicou duas vezes rapidamente no botão e confirmou uma única
  ocorrência tanto no lote quanto em cadastros salvos. Após F5, a ocorrência
  única e o mesmo lote continuaram presentes. O fluxo completo terminou com 14
  verificações e nenhuma exceção JavaScript.
- O teste automatizado também exige que a resposta de cadastro contenha as duas
  listas persistidas e confirma uma ocorrência em cada uma. A suíte permanece
  com **11/11 testes aprovados**.
- Todos os testes usaram banco fictício separado. Nenhum cadastro real ou
  possível duplicado existente foi removido.

## Correção da persistência após F5

- A falha foi reproduzida no Chrome real com banco separado. O cadastro e o
  vínculo com o lote **estavam gravados no SQLite** e `/api/state` os devolvia
  corretamente. O que desaparecia era somente a renderização da tela.
- Causa: `load()` tentava preencher `#smtp-form` por meio de `setForm()`, que
  chama `reset()`. No HTML, porém, `smtp-form` estava aplicado a uma `<div>`.
  A exceção `f.reset is not a function` interrompia o carregamento antes de
  `renderParticipants()`, deixando a lista visualmente vazia após F5.
- `smtp-form` agora identifica o elemento `<form>` correto. Uma falha futura ao
  recuperar o estado mostra uma mensagem persistente e clara, em vez de deixar
  uma lista vazia sem explicação.
- Cadastro e vínculo com o lote agora são gravados na mesma transação. A tela
  confirma sucesso somente depois de receber do backend a lista relida do lote.
- A seleção para geração foi separada da elegibilidade do cadastro e passou a
  ser persistida como `batch_participants.selected`.
- A identificação do lote ativo continua em `settings.current_batch_id`. A
  inicialização não cria lote novo quando já existe um; se a configuração
  estiver ausente ou apontar para lote inexistente, recupera o lote mais recente
  sem apagar ou sobrescrever seus dados.
- Os dados da atividade permanecem em `batches.activity_json`, associados ao
  lote ativo. Apenas a ação explícita `Novo lote` cria outro lote.

### Verificação da correção

- `python -m unittest discover -v`: **11/11 testes passaram**.
- Teste de regressão verifica a estrutura real do formulário e o ciclo completo
  da API: cadastro, vínculo, seleção, atividade e reabertura da aplicação.
- Chrome headless/CDP executou o fluxo real da interface com banco fictício:
  cadastro e vínculo, F5, seleção para geração, F5, atividade, F5, remoção, F5,
  cadastro ainda disponível, geração de certificado e `Novo lote` preservando
  cadastro e histórico. Foram **11 verificações**, sem exceções JavaScript.
- O servidor de teste foi encerrado e iniciado novamente usando o mesmo SQLite;
  nova navegação no Chrome confirmou o mesmo lote ativo, cadastro e histórico,
  além do lote novo vazio e sua atividade vazia.
- O banco principal `data/decip.db` não foi usado nos testes e nenhum dado real
  foi excluído.

## Armazenamento de cadastros, lotes e histórico

### Como era antes

- Os participantes ficavam na tabela `participants` do SQLite
  (`data/decip.db`). O campo persistente `eligible` servia ao mesmo tempo como
  elegibilidade e seleção da tela, portanto não existia um lote atual separado.
- A atividade em edição era uma configuração global (`settings.activity`). Ao
  preparar outra atividade, a mesma lista e a mesma configuração eram
  reaproveitadas.
- Certificados, caminho do PDF, gerações e tentativas de envio já eram
  persistidos nas tabelas `certificates`, `generation_events` e
  `delivery_events`. Esses dados e a numeração sobreviviam ao fechamento do
  navegador e ao reinício do servidor.
- Não havia rotina de limpeza automática no código. Também não havia exclusão
  de cadastro. A inicialização criava um cadastro de demonstração quando o banco
  estava vazio; esse comportamento foi removido.
- A prévia reservava um certificado/código mesmo sem gerar o PDF final. Isso foi
  corrigido: prévia não cria histórico nem consome numeração.

### Como ficou

- **Cadastros salvos:** continuam em `participants` e podem ser reutilizados.
  Exclusão pela interface é arquivamento lógico (`archived_at`), nunca remoção
  silenciosa de certificados, PDFs, eventos ou códigos.
- **Lote atual:** fica em `batches` e `batch_participants`, com atividade e lista
  próprias. `Novo lote` cria uma lista vazia e preserva todo o restante.
- **Histórico de certificados:** continua em `certificates` e nos eventos. A tela
  agora mostra atividade, “PDF gerado” e “E-mail enviado” por certificado.
  Elegibilidade permanece apenas como condição para emissão, sem ser chamada de
  “Concluído”.
- Na primeira abertura após a atualização, a migração é aditiva: cria um lote
  inicial com os participantes antes marcados como elegíveis e copia a atividade
  existente. Nenhum registro anterior é apagado.
- Não existe limpeza automática de cadastros ou histórico.

### Onde estão as opções

- No topo de **Participantes**, `Novo lote` inicia outra atividade. Se houver
  conteúdo não concluído, a interface pede confirmação.
- Em **Lista do lote atual**, `Remover da lista` afeta somente o lote aberto.
- Em **Cadastros salvos**, `Adicionar ao lote` reutiliza uma pessoa sem
  redigitação; `Excluir cadastro` explica o efeito e pede confirmação antes de
  arquivar.
- Em **Resultado**, `Histórico de certificados` identifica a atividade e os
  estados de PDF e envio correspondentes.

## Correção do fluxo e navegação

- O botão antigo ficava abaixo da área inicialmente visível e seu evento apenas
  trocava a seção: não havia guarda para seleção vazia nem mensagem local caso
  o avanço fosse impedido. Isso tornava o resultado do clique ambíguo.
- O e-mail era obrigatório na interface/API e havia um índice único no SQLite,
  acoplando indevidamente a geração de PDF aos dados necessários só para envio.
- As ações Voltar/Continuar agora ficam numa barra inferior persistente, há
  validação visível junto ao ponto correto e a navegação lateral permite voltar
  somente às etapas já alcançadas.
- O e-mail é opcional para PDF. Ausente/inválido aparece como aviso e bloqueia
  exclusivamente o envio daquele destinatário.
- O fluxo agora é: Participantes → Atividade → Revisar/gerar → Resultado. SMTP
  fica oculto até a escolha explícita “Enviar por e-mail”.
- Os dados existentes em `data/decip.db` foram preservados.

## Funciona

- Aplicativo web local em português, restrito a `127.0.0.1:8765`.
- Fluxo em quatro etapas com preenchimento preservado ao navegar.
- Cadastro e edição manual, seleção de elegibilidade e preservação da grafia.
- Importação XLSX com sugestão e confirmação de mapeamento.
- Filtro por presença/elegibilidade, validação de e-mail e duplicidade.
- Validação de obrigatórios, intervalo de datas, horas e atividades (300).
- Dados comuns e sobreposição de função/horas/atividades individuais importadas.
- Prévia usando o mesmo gerador ReportLab do arquivo final.
- PDF A4 paisagem, página única e campos dinâmicos selecionáveis.
- Layout reconstruído com borda, ondas, paleta, rodapé, marca e selo do modelo.
- Código persistente único `DECIP-AAAA-NNNNNN` por participante/atividade.
- Geração individual ou em lote independente de configuração SMTP.
- Registro separado de geração e entrega no SQLite.
- SMTP STARTTLS, anexo individual, teste ao operador e confirmação textual.
- Proteção contra reenvio de lote; uma nova execução pula os já enviados e
  tenta novamente os que falharam.
- Senha salva no cofre do sistema via `keyring`, fora do banco e do código.
- Inicialização simples por `iniciar.bat`.

## Verificações executadas

- `python -m unittest discover -v`: **8/8 passaram**.
- PDF com nome longo: uma página e texto extraível.
- Atividades com 300 caracteres: uma página, sem corte estrutural.
- XLSX fictício: mapeamento, presença, duplicidade e nome preservado.
- SQLite: código estável/único e prevenção de reenvio.
- SMTP simulado: destinatário e anexo individual corretos, sem rede.
- PDF fictício gerado e renderizado em PNG a 1684 × 1191 para inspeção.
- Interface aberta no Chrome headless a 1440 × 1100 e conferida visualmente.
- Teste Chrome/CDP clicou no fluxo completo: seleção vazia, cadastro sem e-mail,
  continuar, voltar, preservação, validação obrigatória, prévia, geração,
  download e bloqueio do envio. **12/12 verificações passaram**, sem exceções JS.

## Arquivos de demonstração

- PDF: `output/Programa_de_Voluntariado_Instituto_DECIP/DECIP-2026-000001-Marina_Oliveira_Santos.pdf`
- Render de inspeção: `output/certificado-exemplo-render.png`
- Captura da interface: `output/interface.png`

## Diferenças visuais conhecidas

- A referência é um JPEG; marca e selo são recortes dessa imagem. PNG/SVG
  originais produzirão contornos mais nítidos.
- A fonte exata não foi fornecida; o PDF usa Helvetica. Métricas e formas das
  letras têm pequenas diferenças.
- Ondas, círculos e geometria inferior foram reconstruídos vetorialmente e têm
  pequenas variações de curva/espessura em relação ao JPEG.
- Os ícones de site, e-mail e validação são simplificados/vetoriais.
- As assinaturas reais ainda não foram fornecidas; há suporte a PNG/JPG por
  caminho local e o exemplo sai sem imagem de assinatura.

Portanto, o resultado é fiel ao modelo e demonstrável, mas não deve ser chamado
de reprodução pixel a pixel enquanto logo, selo, fonte e assinaturas originais
não forem entregues separadamente.

## Limitações e próximos passos

- O andamento de geração/envio é indicado durante a requisição e o relatório
  final traz enviados, ignorados e falhas; progresso por pessoa em tempo real
  ainda requer fila local/SSE.
- A interface permite caminho local para assinatura. A próxima melhoria deve
  adicionar upload e pré-visualização da imagem.
- Ainda não há página pública de validação; a interface não anuncia essa função.
- Envio real não foi executado e depende de credenciais/instrução explícita.
- A exclusão de cadastro é feita por arquivamento; restauração de arquivados
  ainda não tem botão na interface.
- Antes de uso oficial, validar texto institucional, nomes/cargos, contatos e
  fazer prova impressa com os recursos gráficos originais.

### Próxima etapa recomendada

Obter logo e selo em SVG/PNG transparente, a fonte institucional e as duas
assinaturas; substituir os recortes JPEG e fazer uma rodada curta de homologação
visual/impressa. Depois, implementar progresso por pessoa com retry visível.
