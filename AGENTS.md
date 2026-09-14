# AGENTS.md — Agente Multifuncional Orquestrador

Memória de trabalho para futuras sessões neste repositório.

## O que é
Sistema de automação comercial com autoexpansão por scripts/módulos, modo
autônomo controlado, orçamento por tarefa/dia/mês (R$), aprovações humanas
para ações sensíveis e diário de execução. Prioridade: **regras antes de IA**,
LLM econômico depois (somente se configurado via `AE_LLM_*`).

## Estrutura
- `autoexpand/config.py` — constantes centrais + `carregar_config()/salvar_config()`.
- `autoexpand/core/` — persistence (SQLite), registry (versões/rollback),
  budget (limites), approvals (fila humana), journal (diário), execution
  (3 tentativas + anti-loop + bloqueio), permissions/plugin/validation/sandbox_runner.
- `autoexpand/economy/` — llm.py (adaptador desligável) e router.py (3 níveis + cache).
- `autoexpand/orchestrator/` — classifier.py (regras), planner.py (templates),
  executor.py (pipeline pedido→relatório), report.py (formato 11 itens + handoff).
- `autoexpand/browser/` — allowlist + leitor somente leitura.
- `autoexpand/{web,telegram,n8n,android}/` — API Flask, bot Telegram, adaptador n8n
  (mock sem credenciais), contrato Automate (inativo).
- `autoexpand/maintenance.py` — agente de manutenção (ciclo `--ciclo`).
- `main.py` — CLI.

## Comandos
- Testes: `python3 -m pytest -q` (49 testes; deve passar 100%).
- Rodar orquestrador: `python3 main.py "pedido"` (modo padrão: `teste`, nada real).
- Modos: `teste` | `autonomo_controlado` | `producao_protegida` | `emergencia`
  (flag `--modo` ou env `AE_MODO`).
- API: `python3 -m autoexpand.web.api` (porta 8080; token via env `AE_API_TOKEN`).
- Telegram: `python3 -m autoexpand.telegram.bot` (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`).
- Manutenção: `python3 -m autoexpand.maintenance --ciclo`.
- Estado vive em `state/` (SQLite `agente.db`, `config.json`, handoffs `*.md`).

## Invariantes (não quebrar)
1. Site fora da allowlist = bloqueado, nunca auto-incluir domínio.
2. `SEMPRE_APROVAR` nunca executa sem aprovação humana.
3. Limites de custo bloqueiam automaticamente ao ATINGIR (>=), não só ao exceder.
4. Teto: R$ 20/mês · R$ 5/dia · R$ 2/tarefa · 10 chamadas IA/tarefa · 3 tentativas ·
   60 s timeout · 5 páginas.
5. Execução registra sempre no diário (`journal`) e no consumo (`budget`).
6. Sem LLM por padrão; chamar apenas via `economy/router.py` com cache.
7. Handoff salvo a cada execução relevante em `state/handoff-*.md`.

## Convenções
- Modo `teste` simula toda ação externa (não toca rede) — apropriado para CI.
- `pytest` exige `state/` limpo ou ao menos tabelas vazias (fixtures já cuidam).
- Importações: usar caminho absoluto `autoexpand...` (não `..config`) em módulos
  executáveis por `python -m`.

## Referências
- `docs/arquitetura-orquestrador.md` — design dos 8 itens originais.
- `docs/plano-mvp2.md` — plano de fases a..m (todas concluídas em 2026-09-14).
- `docs/manual-operacao.md` — como rodar tudo.
- `docs/contrato-painel.md` — contrato da API consumida pelo painel do usuário.