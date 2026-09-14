# Rodar o Agente Orquestrador no Android (Termux)

## O que é cada peça (respondendo: "Termux ou só Telegram?")

- **Telegram** = o **controle remoto / interface**. Você fala com o bot e ele
  executa pedidos. Para *operar* o agente, **só o Telegram basta** se o agente
  já estiver rodando em algum servidor.
- **Termux** = **onde o agente RODA localmente no seu celular**. É um terminal
  Linux no Android. Necessário apenas se você quiser que o agente viva **dentro
  do seu próprio aparelho**, sem depender de um servidor externo.
- Neste ambiente de desenvolvimento, o agente já roda no servidor (nuvem
  All Hands) → **agora você só usa o Telegram**.

## Quando usar Termux (recomendado para produção no Android)

Se você quiser seu agente "autônomo" rodando 24/7 no celular (sem depender da
nuvem), instale o Termux:

### 1. Instalar
- Baixe o **Termux** na F-Droid (ou GitHub oficial), não na Play Store (versão
  antiga).
```bash
pkg update && pkg upgrade -y
pkg install python python-pip git
pip install flask requests beautifulsoup4 pytest
```
- Ou rode o script pronto: `bash setup_termux.sh` (clona o projeto e prepara o `.env`).

### 2. Obter o código
```bash
git clone SEU_REPO/agente-orquestrador.git
cd agente-orquestrador
```

### 3. Configurar credenciais
```bash
nano .env   # preencha TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID
```

### 4. Rodar os serviços
```bash
./servicos.sh start          # bot + API + manutenção
./servicos.sh status
```

### 5. Manter ativo quando fechar o Termux (opcional)
Use `tmux` para não perder os processos ao minimizar o app:
```bash
pkg install tmux
tmux new -s agente
./servicos.sh start
# Ctrl+b d para desanexar; voltar: tmux attach -t agente
```
Alternativa mais robusta: habilitar "Acorda dispositivo" nas opções do Termux e
usar `termux-wake-lock` (com Termux:API).

## Limitações conhecidas do Termux
- O Android pode pausar processos em segundo plano (bateria). Use `termux-wake-lock`
  e ignore as otimizações de bateria do app.
- O navegador (Playwright) é mais pesado no Android; no MVP a leitura é HTTP
  simples, então funciona.
- Sem systemd no Android → usamos os wrappers `run_*.sh` (auto-restart por loop).

## Resumo da arquitetura de operação
```
TELEGRAM (seu app)  ⇄  bot (polling)  ⇄  agente orquestrador  ⇄  API (painel)
                                                    ⇅
                                          manutenção contínua
```
- Você **comanda pelo Telegram** (pedidos, /aprovado, /status, /emergencia).
- O **agente executa** (classificando, planejando, lendo páginas autorizadas,
  orçando, registrando).
- A **manutenção** cuida da saúde e versões.
- O **Termux** é só o ambiente onde o agente roda, quando você quer local.