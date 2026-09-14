# Manual de Operação — Agente Multifuncional Orquestrador (MVP-2)

## Requisitos
- Python 3.13+, pip; dependências: `flask`, `requests`, `beautifulsoup4`, `pytest`.
- Node instalado para a sandbox JS (opcional no MVP).

```bash
pip install -r requirements.txt   # ou: flask requests beautifulsoup4 pytest
```

## Executar

### Interativo
```bash
python3 main.py
```
Digite pedidos em linguagem natural. `sair` para sair; `emergencia` para pausar tudo.

### Uma execução
```bash
python3 main.py "consulte o preço em https://exemplo.com"
```

### Modos
Por flag (`--modo`) ou variável de ambiente (`AE_MODO`):
- `teste` (padrão): nenhuma ação externa real; leitura simulada.
- `autonomo_controlado`: executa baixo risco sozinho, pede aprovação para sensível.
- `producao_protegida`: reforça aprovações e permite só domínios autorizados.
- `emergencia`: tudo pausado.

### API do painel
```bash
python3 -m autoexpand.web.api &          # porta 8080 (default)
curl localhost:8080/api/limites
```
Auth opcional via variável `AE_API_TOKEN` (Bearer). Endpoints em `docs/contrato-painel.md`.

### Tripé de serviços persistentes (painel + bot + manutenção)
```bash
./servicos.sh start        # sobe os três (bot, API, manutenção)
./servicos.sh stop
./servicos.sh restart
./servicos.sh status
```
Individualmente:
```bash
./run_bot.sh status        # bot Telegram
./run_api.sh status        # API do painel (porta 8080)
./run_maintenance.sh status# agente de manutenção (intervalo via AE_MAINT_INTERVALO)
```
- Cada `run_*.sh` tem `start|stop|restart|status` e auto-restart se o processo cair.
- Logs/PIDs em `state/*.log` e `state/*.pid`.

### Telegram (opcional)
```bash
export TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=...
python3 -m autoexpand.telegram.bot
```
Comandos: `/aprovado <id>` · `/recusar <id>` · `/status` · `/emergencia`.

### Serviço persistente do bot (segunda via quando o painel/navegador falhar)
O bot tem auto-restart independente do navegador/painel: é um serviço à parte
(loop p/ reinício automático).

```bash
./run_bot.sh start      # inicia + mantém vivo (reinicia se cair)
./run_bot.sh stop       # para
./run_bot.sh restart
./run_bot.sh status     # confere (mostra wrapper + processo python)
```

- PID em `state/telegram_bot.pid`; log em `state/telegram_bot.log`.
- Credenciais no `.env` (chmod 600, fora do git): `TELEGRAM_BOT_TOKEN`,
  `TELEGRAM_CHAT_ID`.
- `run_bot.sh` usa apenas `python3` e ferramentas padrão (sem systemd — o ambiente
  é container sem systemd rodando).
- Observação: como depois de remover o webhook os comandos via polling do bot
  funcionam, esta é a segunda via de operação caso o navegador/painel caia.

### Termux vs Telegram (para rodar localmente)
- **Telegram** é sempre o controle remoto: você comanda o agente de qualquer lugar.
- **Termux** (Android) é um ambiente Linux local para *hospedar* o agente no seu
  celular. Só é necessário se você quiser que o agente rode no seu aparelho, sem
  servidor externo.
- Se o agente já está rodando num servidor (como o All Hands), **apenas o Telegram
  basta** para operá-lo.
- Detalhes de instalação no Termux: `docs/rodando-termux.md` (ou `bash setup_termux.sh`).

### Manutenção contínua
```bash
python3 -m autoexpand.maintenance --ciclo
```
Verifica saúde, roda testes, analisa logs, propõe correções (não auto-aplica as de risco).

### Menu rápido (botões) no Telegram
Envie `/menu` (ou `/start`) para abrir o teclado com botões para as funções
essenciais:

- 📚 **Aprender da internet** — você envia o tópico e o agente pesquisa.
- 🧠 **Ensinar (treinar)** — você ensina `tópico: conteúdo`.
- ⚡ **Criar módulo/script** — você descreve e o agente gera + testa + pede
  aprovação.
- 📦 **Meus módulos** / 🗂 **Conhecimentos** / ✅ **Aprovações** — consultas.
- 💵 **Cotação do dólar** — consulta PTAX/BCB na hora.
- 🆘 **Ajuda** / 🔁 **Recomeçar** — auxílio e volta ao menu.

### Treinamento e autoexpansão supervisionada (Telegram)
O agente aprende e se expande **somente com sua supervisão**. Todos os comandos
enviados pelo Telegram:

- `/treinar tópico: conteúdo` — ensina algo diretamente (fica marcado como seu;
  entra como *aprovado* por ser instrução direta sua).
- `/aprender tópico` — o agente **pesquisa na internet** (fonte pública), cria
  um rascunho e **aguarda sua aprovação**.
- `/aprovar_conh <id>` / `/rejeitar_conh <id>` — aprove/rejeite um aprendizado.
- `/conhecimento` — lista o que o agente sabe (aprovados e rascunhos).
- `/criar_modulo <descrição>` — **autoexpansão por script**: o agente gera o
  arquivo em `autoexpand/plugins/`, testa no sandbox e **aguarda sua aprovação**
  para publicar (ação de `publicar_modulo`, sempre supervisionada).
- `/aprovado <id>` / `/recusar <id>` — decide aprovações de publicação de
  módulos e outras ações sensíveis.
- `/modulos` — lista módulos registrados e seu status (rascunho/publicado).
- `/status` — mostra aprovações pendentes + conhecimentos aguardando.

Fluxo completo de expansão: pedido → classificação → geração do rascunho →
teste em sandbox → sua aprovação → publicação versionada (registry). Nenhuma
permissão é auto-concedida.

### Testes
```bash
python3 -m pytest -q
```

## Restrições que valem sempre
- Permissões e limites de custo são aplicados ANTES de qualquer execução.
- Recursão desligada; anti-loop ativo; timeout de 60 s por script.
- Fora da allowlist de domínios = bloqueado (mesmo em modo autônomo).
- Novos domínios só entram pela API/`autorizar_dominio` (com aprovação humana no fluxo do painel).
- Ações em `SEMPRE_APROVAR` nunca executam sem aprovação humana.

## Estado (arquivos)
- `state/agente.db` — SQLite (config, módulos, aprovações, execuções, consumo, diário).
- `state/config.json` — espelho de configuração + domínios autorizados.
- `state/handoff-*.md` — último handoff por execução (retomável).