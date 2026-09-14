"""
Plano de implementação — MVP-2 (fase de código)

Decisões do usuário (confirmadas):
- Modo autônomo controlado: sem confirmação para tarefas internas de baixo risco.
- Ordem fixa: a..m deste documento.
- SQLite no MVP, camada pronta p/ Postgres/Supabase.
- Sem LLM por padrão: regras/templates; adaptador preparado.
- Telegram opcional (token via env), n8n só adaptador, Automate só contrato.
- Painel existente não é reconstruído; cria-se apenas API/adaptador.
- Corrigir "anos 60" → "60 segundos" onde aparecer na documentação.

Limites (constantes centrais em autoexpand/config.py):
  mensal R$ 20 · diário R$ 5 · por tarefa R$ 2 · 10 chamadas IA/tarefa ·
  3 tentativas · timeout 60 s por script · 5 páginas por execução ·
  recursão proibida no MVP · bloqueio automático ao atingir limites.
"""