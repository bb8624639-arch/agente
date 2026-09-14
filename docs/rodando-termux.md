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

### 1. Instalar o Termux
- **Baixe do F-Droid**: `https://f-droid.org/pt/packages/com.termux/`
  (a versão da Play Store é desatualizada e não funciona bem).
- Alternativa: GitHub oficial → `https://github.com/termux/termux-app/releases`.

### 2. Preparar o ambiente
```bash
pkg update && pkg upgrade -y
pkg install python python-pip git nano curl
```

### 3. Obter o código (2 opções)
**Opção A — seu repositório (recomendado p/ manter atualizado):**
```bash
git clone https://github.com/bb8624639-arch/agente.git
cd agente
```
Ou use o script pronto: `bash setup_termux.sh` (já aponta para o repo oficial).

**Opção B — sem repositório ainda (para testar o setup):**
Copie a pasta do projeto (via cabo USB/upload) para `$HOME/agente`.

### 4. Configurar credenciais
```bash
nano .env   # preencha TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID
```

### 5. Instalar dependências
```bash
pip install -r requirements.txt    # ou via setup_termux.sh
python3 -m pytest -q               # 62 testes devem passar
```

### 6. Rodar os serviços
```bash
./servicos.sh start          # bot + API + manutenção
./servicos.sh status
```

### 7. Manter ativo quando fechar o Termux (opcional)
Use `tmux` para não perder os processos ao minimizar o app:
```bash
pkg install tmux
tmux new -s agente
./servicos.sh start
# Ctrl+b d para desanexar; voltar: tmux attach -t agente
```
Alternativa mais robusta: habilitar "Acorda dispositivo" nas opções do Termux e
usar `termux-wake-lock` (com Termux:API)

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