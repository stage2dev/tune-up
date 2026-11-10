// Contrato de GET /api/agentes[?sessao=<id>&todos=1] (frente B: agentes.py + agentes_disco.py).
// Montado por agentes.montar(cfg, sessao=None, todos=False). Resultado guardado por 2 s.
//
// Regras
// - Só sessões de `claude agents --json --all` cujo cwd é a raiz do projeto ou fica dentro dela.
// - sessao: id curto (6-16 hex) ou sessionId (UUID). Outro formato -> sessoes [] e aviso "Sessão inválida.".
// - Sem todos=1: sub-agentes rodando + os que terminaram nos últimos 30 min, no máximo 200 por
//   sessão (rodando primeiro, depois os mais recentes); quando corta, entra um aviso
//   "Sessão <nome>: mostrando 200 de N sub-agentes.". Com todos=1: todos, teto 2000.
// - Nada de texto de pedido ou de resposta: ultima_acao é só nome da ferramenta + nome de arquivo.
// - Datas: ISO 8601 com fuso local, sem frações (ex. "2026-11-10T09:09:57-03:00").

export type EstadoSessao = 'rodando' | 'precisa_de_voce' | 'ocioso' | 'terminou' | 'parada';
export type Esforco = 'low' | 'medium' | 'high' | 'xhigh' | 'max';

export interface Agentes {
  gerado_em: string;
  sessoes: Sessao[]; // ativas primeiro, depois a mais recente
  avisos: string[];
}

export interface Sessao {
  id: string; // id curto do `claude agents` (segundo plano) ou 8 primeiros caracteres do sessionId
  sessao_id: string; // UUID
  nome: string;
  tipo: 'interativa' | 'segundo_plano';
  // Segundo plano: mesmo mapeamento do lançador (state=working + status=idle sem escrita há 180 s = terminou).
  // Interativa parada (status idle) = "ocioso".
  estado: EstadoSessao;
  modelo: string | null; // curto: "opus" | "sonnet" | "haiku" | ...
  esforco: Esforco | null;
  iniciado_em: string | null;
  ultima_atividade: string | null; // última escrita na conversa ou em qualquer sub-agente
  execucao_id: string | null; // id da execução se o painel disparou esta sessão
  agentes_ativos: number; // rodando agora (conta todos, mesmo os que não vieram na lista)
  agentes_total: number; // todos os sub-agentes da sessão no disco
  grupos: Grupo[]; // "direto" primeiro (se houver), depois workflows do mais recente
}

export interface Grupo {
  tipo: 'direto' | 'workflow';
  id: string; // "direto" ou "wf_..."
  nome: string; // "Sub-agentes diretos" ou meta.name do script do workflow (senão o id)
  fases: string[]; // workflow: na ordem do journal; direto: []
  agentes: Agente[]; // por hora de início
}

export interface Agente {
  id: string;
  tipo_agente: string; // meta.agentType (ex. "Explore", "workflow-subagent"); "sub-agente" se faltar
  descricao: string; // meta.description, até 120 caracteres
  fase: string | null; // fase do workflow (journal, senão meta.workflowPhase)
  modelo: string | null; // curto, tirado do id: claude-opus-5-5 -> "opus"
  modelo_id: string | null; // message.model da última resposta; senão meta.model
  esforco: Esforco | null; // meta.effort, senão o último "effort" das linhas
  // workflow: terminou se o journal tem "result"; senão rodando se escreveu há < 120 s ou a sessão está ativa.
  // fora de workflow: meta.finished=true -> terminou; sem finished -> rodando se escreveu há < 120 s.
  estado: 'rodando' | 'terminou';
  profundidade: number; // meta.spawnDepth (1 = criado pela sessão)
  pai_id: string | null; // meta.parentAgentId; senão o agente cujo tool_use Agent/Task tem o toolUseId do meta
  iniciado_em: string | null; // timestamp da primeira linha
  ultima_atividade: string | null; // mtime do .jsonl
  duracao_s: number | null; // até agora se rodando, até a última escrita se terminou
  ferramentas: number; // quantos tool_use o agente fez
  ultima_acao: string | null; // ex. "Edit painel.py", "Bash", "Agent Explore"; máx. 120 caracteres
}
