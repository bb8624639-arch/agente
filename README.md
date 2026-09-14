# Agente Multifuncional Orquestrador

Automação comercial com **autoexpansão supervisionada**: o agente aprende e se
expande por conta própria, mas **nada é publicado sem sua aprovação**.

## Funcionalidades

- **Autoexpansão por script** — descreva a tarefa e o agente gera o módulo
  Python, testa no sandbox e cria uma aprovação pendente.
- **Aprendizado supervisionado** — aprende da internet (Wikipedia REST) ou
  direto com você; o conhecimento vira rascunho até ser aprovado.
- **Menu no Telegram** — botões para aprender, ensinar, criar módulo, listar
  módulos/conhecimentos/aprovações e cotação do dólar.
- **Bot + API + manutenção** como serviços persistentes com auto-restart.
- **Rodando no celular** via Termux (Android) — veja `docs/rodando-termux.md`.

## Comandos principais (Telegram)

| Comando | Descrição |
|---|---|
| `/menu` ou `/start` | Abre o menu de botões |
| `/criar_modulo <descrição>` | Gera um módulo e pede aprovação |
| `/aprovado <id>` | Aprova um módulo pendente |
| `/treinar` | Ensina `tópico: conteúdo` |
| `/aprender <tópico>` | Busca na internet e cria rascunho |
| `/aprovar_conh <id>` / `/rejeitar_conh <id>` | Decide sobre conhecimento |
| `/modulos` | Lista seus módulos |
| `/conhecimento` | Lista o que o agente aprendeu |
| `/cotacao` | Cotação do dólar (PTAX/BCB) |
| `/status` | Saúde do sistema |

## Instalação local

```bash
git clone https://github.com/bb8624639-arch/agente.git
cd agente
pip install -r requirements.txt
# configure .env (veja docs/manual-operacao.md) e rode:
./servicos.sh start
```

No Android/Termux o setup é automatizado: [`setup_termux.sh`](setup_termux.sh) e
guia em [`docs/rodando-termux.md`](docs/rodando-termux.md).

## Testes

```bash
python3 -m pytest -q
```

## Estrutura

- `main.py` — orquestrador e CLI
- `autoexpand/` — núcleo (persistência, conhecimento, executor, classificador,
  planejador, sandbox, registro, orçamento, aprovações, navegador, câmbio,
  bot Telegram)
- `tests/` — suíte de testes
- `docs/` — manuais de operação e guia Termux