# MVP-2 — Orquestrador com Telegram + Leitura de Site Autorizado

Decisões do usuário aplicadas: LLM com adaptador independente (MVP sem LLM real), SQLite,
n8n só adaptador, Telegram como canal, Automate como bridge Android (desenho),
orçamento econômico (R$ 0 ação externa em teste), modo econômico padrão,
local/dev primeiro, leitura de site autorizado, aprovação humana em sensíveis,
Python no núcleo / JS p/ Playwright·n8n, sandbox com limites, versionamento Git+handoff,
painel existente não duplicado (API de integração), credenciais via env/gerenciador.

Status: **proposta de planejamento — aguardando confirmação para implementar.**

---

## 1. Estrutura de diretórios (alvo)

```
autoexpand/
├── __init__.py
├── core/
│   ├── __init__.py
│   ├── permissions.py        (feito)
│   ├── plugin.py             (feito)
│   ├── validation.py         (feito)
│   ├── sandbox_runner.py    (feito)
│   ├── registry.py           (NOVO  versionamento + rollback — SQLite)
│   ├── persistence.py        (NOVO  camada SQLite → Postgres)
│   ├── approvals.py          (NOVO  fila de aprovações + política)
│   ├── budget.py             (NOVO  orçamentos por tarefa/dia/mês + bloqueio)
│   ├── journal.py            (NOVO  logs de execução + consumo estimado)
│   └── execution.py          (NOVO  motor execução: guardas anti-loop, auto-rollback)

├── economy/
│   ├── __init__.py
│   ├── llm.py               (NOVO  adaptador independente de provedor/sempre desligável)
│   ├── router.py             (NOVO  regras→LLM barato→LLM avançado + cache)

├── orchestrator/
│   ├── __init__.py
│   ├── planner.py            (NOVO  interpreta pedido→etapas (regras/templates))
│   ├── classifier.py         (NOVO  classifica objetivo por regras (vendas, android, etc.))
│   ├── executor.py           (NOVO  executa o plano: ferramenta existente → novo script → sandbox)
│   ├── report.py             (NOVO  relatório final no formato 11 itens)
│   └── handoff.py            (NOVO  gera arquivo de handoff por etapa)


├── browser/
│   ├── __init__.py
│   ├── allowed.py            (NOVO  lista de sites autorizados + validação de URL)
 
│   └── reader.py             (NOVO  leitura genérica via HTTP/requests (sem login) —
│                                  Playwright JS/TS em fase posterior)
├── telegram/
│   ├── __init__.py  └── bot.py      (NOVO  bot Telegram: recebe pedido, envia respostas,
│                                          botão aprovar/recusar, status)
├── android/
│   ├── __init__.py  └── automate_bridge.py  (NOVO  contrato Automate webhook HTTPS
├── n8n/
│   ├── __init__.py  └── adapter.py      (NOVO  adaptador REST com credenciais via env)
├── web/
│   ├── __init__.py  └── api.py          (NOVO  API de integração p/ painel existente (emitir
│                                          eventos, listar módulos, consumir aprovações))
├── scripts/                     (plugins/scripts aprovados, versionados)
│   └── exemplos/
├── state/        (gitignored — SQLite, logs, filas)
└── main.py      (NOVO  entrypoint CLI: pergunta→resposta+handoff)

tests/
├── __init__.py
├── test_permissions.py  (feito/estender)
├── test_validation.py    (feito/estender)
├── test_sandbox.py      (feito/estender)
├── test_registry.py     (NOVO)
├── test_budget.py       (NOVO)
├── test_planner.py     (NOVO)
├── test_browser.py      (NOVO)
└── test_approvals.py   (NOVO)
```

---

## 2. Arquivos que serão criados (propósito)

| Arquivo | Propósito |
|---|---|
| `core/persistence.py` | Camada única de banco (SQLite agora, interface idêntica p/ Postgres/Supabase depois). Guarda: módulos, versões, execuções, cronômetro/custos, aprovações. Só **referências** de credenciais. |
| `core/registry.py` | Registro versionado: publicar nova versão nunca sobrescreve estável; `rollback(nome, alvo)` reversível; histórico completo. |
| `core/approvals.py` | Política de aprovação: lista de ações sempre-humanas; fila "aprovado/recusado"; consumível por API/Telegram/painel. |
| `core/budget.py` | Orçamentos tarefa/dia/mês; janela; bloqueio automático ao atingir teto; contadores (chamadas IA, tokens, páginas, mensagens, custo estimado). |
| `core/journal.py` | Log por execução: modelo usado, por que IA foi chamada, nº chamadas, ferramentas, repetições/erros, consumo, como reduzir. |
| `core/execution.py` | Motor: roda plano com timeout, nº máximo de tentativas (3), guardas anti-loop (sem repetição sem mudança de estratégia), interrompe ao bater orçamento; auto-rollback se falhas > tolerância (3). |
| `economy/llm.py` | Adaptador independente de provedor (interface `classificar`, `extrair`, `planejar`, `corrigir`; troca-se o backend via env). **Desligável por padrão** — se sem chave, cai em regras/templates. |
| `economy/router.py` | Roteador 3 níveis: determinístico → LLM barato → LLM avançado, com fallback e cache por chave de entrada. |
| `orchestrator/classifier.py` | Classifica pedido **só por regras** (palavras-chave/objetivo): vendas, pesquisa, navegador, android, db, loja, criar_agente, erro. Sem IA no caminho quente. |
| `orchestrator/planner.py` | Gera plano de etapas a partir do pedido (templates por classe); inclui ferramentas, permissões, custo estimado, riscos, aprovações exigidas). Se algo não mapeia → LLM avançado (se habilitado); senão devolve "não sei + próximas perguntas". |
| `orchestrator/executor.py` | Orquestra: verifica catálogo → sandbox → aprovação → produção; coleta resultado. |
| `orchestrator/report.py` | Relatório final nos 11 campos: objetivo, plano, agentes, ferramentas, permissões, custo, riscos, aprovações, resultado dos testes, próxima ação, relatório de execução. |
| `orchestrator/handoff.py` | Gera `handoff-<data>.md` (JSON legível) por etapa: decisões, versões, pendências, próximos passos. |
| `browser/allowed.py` | Lista de domínios autorizados (default vazia — usuário preenche); valida URL: só `https`, sem IP bruto, sem localhost, sem credenciais na URL. |
| `browser/reader.py` | Tarefa genérica de leitura: {url autorizada, seletor/instrução, limite de páginas (5), timeout (60s), formato de saída}. Usa `requests`/`BeautifulSoup` (sem JS) no MVP. |
| `telegram/bot.py` | Bot Telegram com polling simples (sem lib pesada: `requests`); recebe pedido → devolve plano → botões aprovar/recusar → resultado → handoff. Token só via env. |
| `android/automate_bridge.py` | Contrato Automate (webhook HTTPS, intents, notificações,ações conhecidas); inativo no MVP-hit só desenho+validação de payload. |
| `n8n/adapter.py` | Adaptador claro: `criar_workflow(nome, nós, credencial_ref)`; não conectado no MVP; credenciais via env; testado com mock. |
| `web/api.py` | Endpoint de integração p/ painel existente: `GET /modulos`, `GET /aprovacoes`, `POST /aprovacoes/:id`, `POST /emergencia`; contrato documentado em `docs/contrato-painel.md`.(sem duplicar o painel). |
| `main.py` | CLI interativo: pedido → resposta (11 campos) → handoff. |

---

## 3. Ferramentas necessárias

| Ferramenta | Uso | Já disponível? |
|---|---|---|
| Python 3.13 | núcleo | ✅ |
| pip | instalar deps | ✅ |
| `requests` | HTTP (browser/reader, telegram) | precisa instalar |
| `beautifulsoup4` | parser de HTML p/ leitura autorizada | precisa instalar |
| `pytest` | testes | ✅ (já instalado) |
| Flask | `web/api.py` (opcional no MVP) | ✅ |
| Node 22 | Playwright (fase posterior — **não no MVP**) | ✅ |
| SQLite | estado (stdlib `sqlite3`) | ✅ |
| Git | versionamento | ✅ |

Não instalar: Playwright, Appium, ADB, n8n, WhatsApp — fase posterior.

---

## 4. Permissões de cada módulo

| Módulo | Permissões que declara | Efeitos | Aprovação? |
|---|---|---|---|
| `browser/reader` | `rede`, `ler_api` (lectura de site autorizado) | só GET/leitura | automática (site na lista) |
| `browser/reader` p/ site **não** autorizado | `rede` + nova entrada na lista | acesso a site novo | **sim** |
| `orchestrator/planner` | — (somente leitura de catálogo/local) | nenhum efeito | automática |
| `core/registry` (publicar versão) | `escrever_db` | publicação de módulo | **sim** |
| `core/registry` (rollback) | `escrever_db` | reversão de versão | sim (registrado; reversível) |
| `telegram/bot` (enviar resposta) | `mensagens` (1:1 com solicitante) | respostas ao dono | automática (restrito a chat autorizado) |
| `telegram/bot` (notificar terceiros) | `mensagens` (em massa) | contato com clientes | **sim** |
| `android/automate_bridge` | `sistema` (device) | execução no Android | **sim** (MVP: inativo) |
| `n8n/adapter` | `chamar_api` + `credenciais` (ref) | criar workflows | **sim** (MVP: mock) |
| `core/budget` (bloquear) | — (leitura de contadores) | nenhum efeito | automática |
| `core/approvals` | `escrever_db` | fila de aprovações | registrado (quem aprovou) |
| `main.py` (CLI) | (herda do plugin invocado) | — | conforme o plugin |

Regra global: **nenhum módulo tem permissão além da declarada**; `PacotePermissao` (já em `sandbox_runner.py`) corta o que não foi concedido. `escrever_*`, `mensagens` (massa), `pagamentos`, `credenciais`, `publicar`, `sistema` estão na lista always-human (feita em `permissions.py`).

---

## 5. Limites de custo / consumo

| Limite | Valor default | Onde |
|---|---|---|---|
| Orçamento mensal de IA | R$ 20,00 | `state/budget.json` via `core/budget.py` |
| Orçamento diário de IA | R$ 5,00 (configurável) | idem |
| Orçamento **por tarefa** | R$ 2,00 | idem |
| Chamadas de IA por tarefa | 10 | `core/budget.py` |
| Tentativas por ação | 3 | `core/execution.py` |
| Timeout por script | 60 s (default 30 s) | manifesto + `core/sandbox_runner.py` |
| Páginas visitadas por execução | 5 | `browser/reader.py` |
| Custo de ação externa no **modo teste** | R$ 0,00 (nenhuma ação externa) | `core/budget.py` |
| Chamadas recursivas | 0 (proibidas no MVP) | `core/execution.py` |
| Repetições sem mudança de estratégia | impedidas após 1ª | `core/execution.py` |
| Ações sensíveis | sempre bloqueadas até aprovação | `core/approvals.py` |

Modos: `teste` (padrão: R$ 0 externo, tudo simulado), `aprovacao_manual` (tudo sensível para humano), `producao` (só aprovado; orçamento ativo). Botão de emergência: zera fila e pausa tudo (`POST /emergencia` ou `main.py --emergencia`).

---

## 6. Testes planejados

| Teste | Verifica |
|---|---|
| `test_registry.py` | publicar nunca sobrescreve estável; rollback restaura versão; histórico cresce |
| `test_budget.py` | bloqueia ao atingir teto diário/mensal/tarefa; zera janela; emergência pausa |
| `test_approvals.py` | ação sensível sem aprovação é bloqueada; aprovação registra quem/quando |
| `test_planner.py` | pedido "consulte preço em site autorizado" → plano de leitura correto; sem LLM |
| `test_classifier.py` | classifica por regras (vendas, android, db, erro…) sem IA |
| `test_browser.py` | site não autorizado é bloqueado; URL malformada rejeitada; limite de páginas |
| `test_execution.py` | tentativas > 3 param; loop sem mudança de estratégia bloqueia; auto-rollback após falhas |
| `test_handoff.py` | handoff gerado contém versões, pendências, próxima ação |
| `test_sandbox.py` (estender) | timeout, memória, kill em loop (`while True`) |

Manuais: rodar `main.py` com pedido de leitura autorizada (ex.: `httpbin.org/anything` após autorizar domínio), confirma bloqueio de site não autorizado, aprovar/recusar via bot Telegram e handoff gerado.



---

## 7. Riscos e mitigações

| Risco | Mitigação |
|---|---|
| LLM gera texto incoerente/caro | MVP **sem LLM** por padrão; regras/templates; adaptador desligado sem chave; teto R$ 20/mês |
| Site autorizado muda layout | leitura genérica por seletor/instrução + timeout + modo teste; falha → relatório honesto (não inventar sucesso) |
| Vazamento de credenciais | só env vars; nunca em prompts/logs/docs; banco guarda só referência; logs redigem padrões tipo `token=...`, `Authorization:` |
| Script cria loop / consome CPU | sandbox com RLIMIT_CPU/memória; timeout 60 s; kill forçado; teste de loop no suite |
| Bug em produção | versão nova, nunca sobrescreve estável; rollback automático se falhas > 3; handoff por etapa |
| Pedido ambíguo | executor devolve "não sei" + perguntas (sem inventar ação) |
| Apagamento acidental | `escrever_db`/exclusão é sensível → aprovação; backups via Git/versões |
| Consumo acima do teto | `core/budget.py` interrompe no limite; todo passo conta no journal |
| Painel externo quebra integração | contrato API documentado; painel é cliente consumidor; núcleo segue independente |
| Android Automate inseguro | **inativo no MVP**; contrato projetado; ativação só sob aprovação e depois de teste |

---

## 8. Instruções exatas para executar o MVP

```bash
# 0. Pré-requisitos
cd /workspace/project
python3 -m venv .venv && source .venv/bin/activate
pip install --quiet requests beautifulsoup4 pytest flask

# 1. Rodar os testes
pytest -q

# 2. (Opcional) autorizar um domínio para leitura
#     Abrir state/config.json e adicionar, ex.:
#     {"dominios_autorizados": ["httpbin.org"]}

# 3. Rodar o orquestrador em modo interativo
python3 main.py
#     Pedido de exemplo:
#     "consulte a página https://httpbin.org/anything e retorne o campo args"
#     (URL autorizada; sem login; modo teste: retorno simulado impresso)

# 4. Ver o handoff gerado
ls state/handoff-*.md
cat state/handoff-*.md

# 5. (Opcional) API de integração para o painel existente
flask --app autoexpand.web.api run --port 8080 &
curl -s localhost:8080/api/modulos

# 6. (Opcional) Telegram — só com token em env
export TELEGRAM_BOT_TOKEN=...; export TELEGRAM_CHAT_ID=...
python3 -m autoexpand.telegram.bot
#     Enviar o mesmo pedido no Telegram → resposta no formato 11 campos
```

Modo padrão: **`teste`**. Para trocar: `export AE_MODO=aprovacao_manual` (ou `producao`).
Botão de emergência: `python3 main.py --emergencia`.

---

## Pendências que bloqueiam fases futuras (não bloqueiam o MVP):

- Conectar n8n (URL + credencial API)
- Conectar WhatsApp Business (Meta/config comercial)
- Android Automate real (HTTPS acessível ao aparelho, domínio/DDNS, intents reais)
- Múltiplos usuários → migrar SQLite → PostgreSQL/Supabase
- Playwright/JS (quando for preciso JS/assinatura no site autorizado)