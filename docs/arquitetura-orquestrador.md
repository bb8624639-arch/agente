# Agente Multifuncional Orquestrador — Arquitetura (MVP)

Status: **proposta de design — aguardando respostas do questionário antes da implementação completa.**
O código em `autoexpand/core/` é um esqueleto funcional (permissões, manifesto, validação, sandbox).

---

## 1. Visão geral

Um **orquestrador único** recebe o pedido em linguagem natural, entende o objetivo,
divide em etapas, seleciona/cria agentes especializados e ferramentas, e só executa
o que estiver dentro das permissões, orçamento e modo do sistema.

```
Você / Painel / Telegram
        │
        ▼
┌─────────────────────────┐
│  ORQUESTRADOR (núcleo)  │  1. Interpretar  2. Plano  3. Agentes  4. Executar
└─────────────────────────┘
        │
        ├─ Roteador econômico (determinístico primeiro → LLM barato → LLM avançado)
        ├─ Catálogo de ferramentas/módulos (plugins) — já criados ou novos
        ├─ Registro versionado + rollback
        ├─ Sandbox de testes (isolado)
        ├─ Painel de aprovação humana
        └─ Sistema de custos/orçamento
        │
        ▼
   Execução em produção (mode: teste | aprovação_manual | produção)
   ├── n8n   ├── APIs autorizadas   ├── Banco de dados
   ├── Playwright (navegador)      ├── Automate/Appium/UIAutomator2/ADB (Android)
   └── Scripts Python/JavaScript   └── WhatsApp Business / Telegram
```

### Princípios inegociáveis

1. Nenhum código arbitrário roda em produção sem passar por **sandbox + aprovação**.
2. Cada execução tem **timeout**, **orçamento** e **limite de tentativas** — sem loops.
3. Toda mudança é **versionada**; nunca se sobrescreve a versão estável — publica-se
   uma nova versão e **rollback** é um clique.
4. Credenciais **nunca** aparecem em prompts, logs, relatórios ou respostas.
5. Ações sensíveis (pagamentos, exclusões, envio em massa, credenciais, mensagens)
   **sempre** exigem um humano.
6. Prefere-se **código determinístico e APIs** antes de IA e automação visual.

---

## 2. Diagrama dos componentes

```
┌─────────────── Solicitantes ───────────────┐
│  Painel Web  │  Telegram  │  WhatsApp  │  API  │
└──────────────┬─────────────────────────────┘
               ▼
┌───────────────────────────────────────────────────────┐
│  CAMADA DE ENTRADA  — validação, auth, rate limit      │
│  (regras, sem IA)                                      │
└──────────────────────┬────────────────────────────────┘
                       ▼
┌───────────────────────────────────────────────────────┐
│  ORQUESTRADOR                                          │
│  ├─ Compreensão do pedido      (LLM barato p/ triagem) │
│  ├─ Verificação de ferramenta existente  (catálogo)    │
│  ├─ Roteamento determinístico  (regras, sem IA)        │
│  ├─ Plano de execução          (etapas + custo)        │
│  └─ Dispatcher (uma fila, pausa no custo/aprovação)    │
└──────┬───────────────┬────────────────┬────────────────┘
       │               │                │
       ▼               ▼                ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────────┐
│ CAPACIDADES  │ │ ™ AGENTES    │ │ SEGURANÇA/CUSTO  │
│ (plugins)    │ │ ESPECIALIZ.  │ │                  │
│ CSVOnline    │ │ planejamento │ │ permissions      │
│ n8n          │ │ vendas       │ │ sandbox          │
│ Playwright   │ │ produtos     │ │ registro/versões │
│ Android      │ │ pedidos      │ │ aprovação humana │
│ APIs/DB      │ │ estoque      │ │ orçamento/cache  │
│ scripts      │ │ marketing    │ │ journal de uso   │
│              │ │ pesquisa     │ │ botão de pânico  │
│              │ │ navegador    │ │                   │
│              │ │ android      │ │                   │
│              │ │ programador  │ │                   │
│              │ │ testes       │ │                   │
│              │ │ segurança    │ │                   │
│              │ │ custos       │ │                   │
│              │ │ decíduo      │ │                   │
│              │ │ recuperação  │ │                   │
└──────────────┘ └──────────────┘ └──────────────────┘
```

---

## 3. Modelo de capacidades

Cada agente especializado é descrito por um **manifesto** (o mesmo formato de plugin
do resto do sistema). O orquestrador **cria ou reutiliza** agentes conforme a demanda.

```json
{
  "nome": "agente_pedidos",
  "versao": "1.0.0",
  "funcao": "Atualizar status de pedidos e alertar o time de vendas",
  "perfil": "rascunho",
  "permissoes": ["ler_pedidos", "escrever_pedidos", "mensagens"],
  "requer_aprovacao": true,
  "input_schema": {"type": "object", "properties": {"pedido_id": {"type": "string"}}, "required": ["pedido_id"]},
  "output_schema": {"type": "object", "properties": {"status": {"type": "string"}}, "required": ["status"]},
  "timeout_seconds": 60,
  "limite_memoria_mb": 256,
  "tolerancia_falhas": 3,
  "monitorado": true
}
```

Capacidades nativas do orquestrador (bridge — **nunca** LLM quando houver API):

| Capacidade | Custo preferido | Exige aprovação? |
|---|---|---|
| n8n (criar workflow via API) | determinístico + LLM barato p/ traduzir natural→JSON | sim (publicar) |
| Banco de dados (SQL) | determinístico | escrita: sim; leitura: não |
| Loja / painel web (integrações autorizadas) | APIs determinísticas | dep. da ação |
| Vendas (CRM / e-mail / WhatsApp) | APIs | envio: sempre sim |
| WhatsApp Business (API oficial) | API | sempre sim |
| Telegram (bot) | API | envio: sempre sim |
| Playwright | código + run do navegador | se acesso a site |
| Automate / Appium / UIAutomator2 / ADB | código | sim (device) |
| Scripts Python/JS | código no sandbox | se efeitos |
| APIs externas não autorizadas | **bloqueado** até entrada na lista de autorizados + aprovação | — |
| Conectores novos (API/site/DB) | geração via LLM + validação | sim |

### Tipos de agents especializados e suas permissões

| Agente | Permissões típicas | Decisão requerida (humana?) |
|---|---|---|
| planejamento | ler_* | — |
| vendas | ler_pedidos, mensagens | envio sim |
| produtos | ler_db, escrever_db | escrita sim |
| pedidos | ler_pedidos, escrever_pedidos | escrita sim |
| estoque | ler_db, escrever_db | escrita sim |
| marketing | ler_db, mensagens | envio sim |
| pesquisa | ler_api, rede | — |
| navegador | navegador, rede | site novo sim |
| android | sistema (adb/appium) | sim |
| programador | instalar_pacotes (só sandbox) | publicar sim |
| testes | (somente sandbox) | — |
| segurança | auditoria (leitura) | — |
| custos | leitura do journal | — |
| decíduo (data) | ler_db | — |
| recuperação de erros | leitura + reverter | rollback sim |

---

## 4. Estrutura de plugins (manifesto)

O formato já iniciado no repo (`autoexpand/core/plugin.py`, `permissions.py`):

```json
{
  "nome": "consultar_pedido",
  "versao": "1.0.0",
  "description": "Consulta um pedido autorizado",
  "runtime": "javascript",
  "permissoes": ["ler_pedidos"],
  "requer_aprovacao": false,
  "input_schema": {},
  "output_schema": {},
  "timeout_seconds": 30
}
```

Ciclo de vida de um plugin:

```
rascunho ──valida──► testado ──aprovação humana──► publicado ──► desativado/removível
   ▲                                                              │
   └────────────────────── nova versão (nunca sobrescreve) ◄──────┘
```

- **Permissões são declaradas** no manifesto; o runtime **não auto-concede** nada que
  não exista no catálogo global (regra 12 do spec anti-decepção).
- **Entrada/saída padronizadas**: `entrada()` / `saida()` no Python; `entrada()` /
  `saida()` no JavaScript (contrato JSON).
- **Teste obrigatório** no sandbox antes de `publicado`.
- **Rollback**: qualquer versão publicada é reversível em 1 clique no painel.

---

## 5. Fluxo de aprovação

```
Pedido do humano
   │
   ▼
1. ORQUESTRADOR interpreta e planeja (LLM barato; avançado só se preciso)
2. Verifica: existe ferramenta/fluxo? (catálogo — determinístico, barato)
3. Mostra: plano, agentes, ferramentas, permissões, custo estimado, riscos
   │
   │  ação sensível? (pagamento, envio, exclusão, credenciais, publicar,
   │                  acesso a site/API não autorizado, criar workflow n8n)
   │
   ▼
4. TESTE EM SANDBOX — ocorre SEMPRE para código novo (sem aprovação)
5. Apresenta resultado do teste ao humano
   │
   ▼
6. APROVAÇÃO HUMANA no painel/Telegram
   │
   ▼
7. Publica versão controlada (registro)
8. Executa em produção sob orçamento/timeout/modo
9. Monitora; se falha além da tolerância → ROLLBACK automático
10. Relatório final (modelo usado, chamadas, custo, ferramentas, repetições/erros)
```

**O que NÃO precisa de humano** (automatizável): triagem, roteamento, validação,
sandbox/testes, cálculo de custo, cache, sumarização, monitoramento, rollback
automático, versionamento, relatório. **(Sempre humano:)** qualquer ação com efeito
irreversível, custo alto, envio de mensagens/pagamento, acesso a recurso novo,
publicação de módulo, alteração de credenciais.

---

## 6. Sistema de custos / economia

- Roteador **3 níveis**: regra determinística → modelo barato → modelo avançado
  (com fallback e justificativa registrada).
- **Cache** por chave de entrada (resultados idempotentes reutilizados).
- Orçamentos: **por tarefa, diário, mensal** — o executor para automaticamente.
- **Journal** registra por execução: modelo, quantas chamadas, tokens, ferramentas
  acionadas, repetições/erros, custo estimado (e como reduzir).
- Prévia de custo **antes** de tarefas caras; aprovação exigida acima de teto.
- Contadores no painel: chamadas IA, tokens, dedos, tempo de navegador, mensagens, custo.
- Bloqueios automáticos: loops, recursões, esforços repetidos sem mudança de estratégia,
  envio em massa, navegador sem objetivo, agentes redundantes, scripts não testados.

---

## 7. Primeiro MVP (escopo: o que implementar primeiro)

**Fase A — Núcleo (já iniciado):**
1. Manifesto/validação de permissões (feito).
2. Sandbox de execução Python + JavaScript com limites (feito).
3. Registro versionado com rollback.
4. Aprovação humana (fila de aprovações em arquivo, consumida por curl/API).

**Fase B — Economia & segurança:**
5. Roteador determinístico-primeiro + cache + journal de custos.
6. Guardas anti-loop e auto-rollback.

**Fase C — Superfície:**
7. Painel web (Flask) com: módulos (ativar/desativar/excluir), aprovações,
   orçamentos, contadores, modo teste/aprovação/manual/produção, botão de emergência.
8. Conector n8n (criar workflow por API) e Playwright (via Node).

**Fase D — Android & expansão:**
9. Conectores Automate/ADB (bridge mínima) e Appium (projeto separado).
10. Gerador por fases 1–6 (script simple → ferramenta → workflow → conector →
    sugestão de módulo → implantação após aprovação).

Repositório atual tem Fases A1, A2 e parte de A3. **Antes de prosseguir com as
fases B/C, é preciso responder o questionário abaixo.**

---

## 8. Perguntas para você (decisões de arquitetura)

1. **Onde rodam os LLMs?** Conta própria em qual provedor (OpenAI, Anthropic,
   Google, local via Ollama)? Precisamos definir o modelo "barato" e o "avançado"
   e a moeda/custo por token. *(Se não usar LLM ainda, o MVP pode rodar 100%
   com regras + templates — me diga.)*
2. **Onde fica o estado?** Arquivos locais (SQLite) são suficientes para o MVP, ou
   exige PostgreSQL/Supabase na nuvem com painel multi-usuário?
3. **O n8n já está instalado?** Versão, URL e se há API habilitada (credencial de
   API). O orquestrador fala com n8n via REST; preciso saber o endpoint.
4. **Como você acessa o WhatsApp Business?** API oficial Cloud (Meta), provedor
   parceiro (Twilio, etc.) ou baixar a fita? Quais números/credenciais?
5. **Telegram:** já tem um bot criado com o BotFather? Token?
6. **Loja/painel web atual:** qual é (Shopify, WooCommerce, Bling, Tiny, própria)?
   Existe API/credenciais? O painel atual (`agente-dash-...manus.space`) usa qual backend?
7. **Android:** os aparelhos ficam ligados via USB/ADB numa máquina, ou usam
   Automate via webhook na própria rede? Quais apps/versões?
8. **Sites autorizados para scraper:** qual lista inicial de domínios você autoriza?
9. **Credenciais/integrações existentes:** quais já existem (bancos, ERP, CRM)?
10. **Modos de segurança:** confirma que "teste" e "aprovação manual" devem ser
    padrão ao instalar, e "produção" só por escolha explícita?
11. **Orçamento financeiro inicial:** qual o teto por **operación/tarefa**, por **dia**
    e por **mês** (na moeda desejada)?
12. **Acesso humano ao painel:** quantas pessoas, papel de aprovação único? Haverá
    senha única ou Google OAuth?
13. **Nível de isolamento do sandbox:** subprocesso com limites (rápido, MVP) ou
    Docker/containers (mais seguro, mais lento)? O host tem Docker?
14. **Deploy do orquestrador:** onde roda (VPS, Docker, o próprio servidor do n8n)?
    Precisa do painel público naquele domínio `manus.space` ou posso servir
    localmente?
15. **Importação do painel existente:** quer que eu **ignore** o painel publicado e
    construa um novo no repo, ou prefere manutenção/evolução daquele (que está num
    espaço Manus diferente e sem código acessível por aqui)?
16. **Banco de dados comercial:** banco de dados real (postgres) com schema, ou
    planilha/arquivo JSON no início? Qual sistema de loja/estoque/pedidos?