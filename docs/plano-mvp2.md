"""
Plano de implementação — MVP-2 (fase de código)

DECISÕES DO USUÁRIO (confirmadas):
- Modo autônomo controlado: sem confirmação para tarefas internas de baixo risco.
- Ordem fixa: a..m deste documento.
- SQLite no MVP, camada pronta p/ Postgres/Supabase.
- Sem LLM por padrão: regras/templates; adaptador preparado (economia/llm.py).
- Telegram opcional (token via env), n8n só adaptador, Automate só contrato.
- Painel existente não é reconstruído; cria-se apenas API/adaptador (docs/contrato-painel.md).

LIMITES (constantes centrais em autoexpand/config.py):
  mensal R$ 20 · diário R$ 5 · por tarefa R$ 2 · 10 chamadas IA/tarefa ·
  3 tentativas · timeout 60 s por script · 5 páginas por execução ·
  recursão proibida no MVP · bloqueio automático ao atingir limites.
  (O teto é atingido EXATAMENTE também bloqueia; ver core/budget.py.)

ESTADO DO IMPLEMENTAÇÃO (2026-09-14):
  [x] a. Persistência e registro versionado ............ core/, registry (publicar/rollback/versao_atual)
  [x] b. Orçamento e limites ........................... core/budget.py (tarefa/dia/mês, chamadas, páginas)
  [x] c. Aprovações e diário ........................... core/approvals.py, core/journal.py
  [x] d. Executor seguro ............................... core/execution.py (3 tentativas, anti-loop, bloqueio)
  [x] e. Classificador ................................. orchestrator/classifier.py (regras, sem IA)
  [x] f. Planejador .................................... orchestrator/planner.py (templates + devolver não-sei)
  [x] g. Relatório e handoff ........................... orchestrator/report.py (11 campos + estado retomável)
  [x] h. Navegador somente leitura ..................... browser/, allowlist em config
  [x] h2. Orquestrador + CLI ........................... orchestrator/executor.py, main.py
  [x] i. API para painel ............................... web/api.py + docs/contrato-painel.md
  [x] j. Telegram opcional ............................. telegram/bot.py (polling, TELEGRAM_BOT_TOKEN)
  [x] k. Integração n8n (adaptador/mock) ............... n8n/adapter.py (sem credenciais → mock)
  [x] l. Automate Android (contrato só) ................ android/automate_bridge.py (valida payload)
  [x] m. Manutenção contínua ........................... autoexpand/maintenance.py (ciclo --ciclo)
  [x] Testes automatizados ............................. tests/ (49 testes; pytest -q)
  [x] Commit do progresso

PENDENTE (fora do MVP-2 / próximas fases):
  - Conectar LLM econômico real (o adaptador já está; definir provider custo-baixo).
  - Playwright/Chromium para páginas com JS.
  - Automate ativo com app Android (webhook assinado).
  - n8n ativo com REST API real (N8N_URL + N8N_API_KEY).
"""