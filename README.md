# Agente Multifuncional Orquestrador

Automação comercial com **autoexpansão supervisionada**: o agente aprende e se
expande por conta própria, mas **nada é publicado sem sua aprovação**.

## Funcionalidades

- **Autoexpansão por script** — descreva a tarefa e o agente gera o módulo
  Python, testa no sandbox e cria uma aprovação pendente.
- **Aprendizado supervisionado** — aprende da internet (Wikipedia REST +
  fallback DuckDuckGo) ou direto com você; o conhecimento vira rascunho até
  ser aprovado.
- **Pesquisa na internet total** — comando `/pesquisar` busca em qualquer
  termo (DuckDuckGo); páginas só são abertas se o domínio estiver autorizado.
- **Contexto colado** — cole um texto/documento inteiro no chat (ou use
  `/contexto`) e o agente importa tudo como conhecimento (até 30 mil chars).
- **Capacidade de pensar** — `/pensar` sintetiza o que o agente aprendeu,
  mostra execuções/erros recentes e sugere próximos passos (raciocínio
  determinístico, sem LLM).
- **Conversa avançada** — `/conversa` permite conversar com o agente; ele
  responde com base no que aprendeu (e é honesto quando não sabe).
- **Ideologia** — `/ideologia` explica os princípios que guiam o agente
  (autonomia com supervisão, verdade verificável, custo consciente).
- **Método dos Sete Portais** — `/portais <problema>` resolve problemas com
  uma abordagem estruturada de 7 perspectivas (Enigma, Visão, Inspiração,
  Inusitado, Escolha, Execução, Reflexão).
- **Autosave no GitHub** — quando você aprova conhecimento/cria módulo, o
  agente exporta a memória (`docs/agente-memoria.md`) e faz commit+push
  automaticamente (instalação local/Termux). Desligue com `AE_GIT_AUTOSAVE=0`
  ou `/desligar_autosave`.
- **Botão fixo de START no Telegram** — barra persistente (ReplyKeyboard)
  sempre visível com atalhos para todas as ações.
- **Menu no Telegram** — botões para aprender, ensinar, pesquisar, pensar,
  criar módulo, listar módulos/conhecimentos/aprovações e cotação do dólar.
- **Bot + API + manutenção** como serviços persistentes com auto-restart.
- **Rodando no celular** via Termux (Android) — veja `docs/rodando-termux.md`.

## Comandos principais (Telegram)

| Comando | Descrição |
|---|---|
| `/menu` ou `/start` | Abre o menu de botões + barra fixa de START |
| `/criar_modulo <descrição>` | Gera um módulo e pede aprovação |
| `/aprovado <id>` | Aprova um módulo pendente |
| `/treinar` | Ensina `tópico: conteúdo` |
| `/aprender <tópico>` | Busca na internet (Wikipedia → DuckDuckGo) e cria rascunho |
| `/pesquisar <termo>` | Pesquisa livre na internet (DuckDuckGo) |
| `/pensar [pergunta]` | Sintetiza conhecimentos e sugere próximo passo |
| `/contexto <texto>` | Importa texto colado grande como conhecimento |
| `/conversa` | Conversa com o agente (responde com base no que aprendeu) |
| `/portais <problema>` | Resolve problema pelo método dos Sete Portais |
| `/ideologia` | Mostra os princípios do agente |
| `/autosave` | Força commit+push do aprendizado no GitHub |
| `/aprovar_conh <id>` / `/rejeitar_conh <id>` | Decide sobre conhecimento |
| `/modulos` | Lista seus módulos |
| `/conhecimento` | Lista o que o agente aprendeu |
| `/cotacao` | Cotação do dólar (PTAX/BCB) |
| `/status` | Saúde do sistema + resumo do agente |

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