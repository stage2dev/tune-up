// Tipos e busca de GET /api/agentes (sessoes do Claude neste projeto e os sub-agentes delas).
// Contrato fixo da Frente C: o servidor manda so sessoes cujo cwd fica dentro da raiz do projeto.
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { apiGet } from './cliente';

export type EstadoSessao = 'rodando' | 'precisa_de_voce' | 'ocioso' | 'terminou' | 'parada';
export type Esforco = 'low' | 'medium' | 'high' | 'xhigh' | 'max';

export interface AgenteVivo {
  id: string;
  tipo_agente: string;
  descricao: string;
  fase: string | null;
  /** Curto: "opus", "sonnet", "haiku" ou outro texto. */
  modelo: string | null;
  modelo_id: string | null;
  esforco: Esforco | string | null;
  estado: 'rodando' | 'terminou';
  profundidade: number;
  pai_id: string | null;
  iniciado_em: string | null;
  ultima_atividade: string | null;
  duracao_s: number | null;
  ferramentas: number;
  /** So nome da ferramenta + nome de arquivo (ex.: "Edit painel.py"). */
  ultima_acao: string | null;
}

export interface GrupoAgentes {
  tipo: 'direto' | 'workflow';
  id: string;
  nome: string;
  fases: string[];
  agentes: AgenteVivo[];
}

export interface SessaoClaude {
  id: string;
  sessao_id: string;
  nome: string;
  tipo: 'interativa' | 'segundo_plano';
  estado: EstadoSessao;
  modelo: string | null;
  esforco: Esforco | string | null;
  iniciado_em: string | null;
  ultima_atividade: string | null;
  execucao_id: string | null;
  agentes_ativos: number;
  agentes_total: number;
  grupos: GrupoAgentes[];
}

export interface RespostaAgentes {
  gerado_em: string;
  sessoes: SessaoClaude[];
  avisos: string[];
}

export const chaveAgentes = (todos: boolean) => ['agentes', todos ? 'todos' : 'ativos'] as const;

export function urlAgentes(todos: boolean, sessao?: string): string {
  const q = new URLSearchParams();
  if (sessao) q.set('sessao', sessao);
  if (todos) q.set('todos', '1');
  const s = q.toString();
  return s ? `/api/agentes?${s}` : '/api/agentes';
}

/** Normaliza o que chegou: campos que faltam viram listas vazias, nunca quebram a tela. */
export function normalizarAgentes(bruto: unknown): RespostaAgentes {
  const r = (bruto && typeof bruto === 'object' ? bruto : {}) as Partial<RespostaAgentes>;
  const sessoes = Array.isArray(r.sessoes) ? r.sessoes : [];
  return {
    gerado_em: typeof r.gerado_em === 'string' ? r.gerado_em : '',
    avisos: Array.isArray(r.avisos) ? r.avisos.filter((a): a is string => typeof a === 'string') : [],
    sessoes: sessoes.map((s) => ({
      ...s,
      grupos: (Array.isArray(s.grupos) ? s.grupos : []).map((g) => ({
        ...g,
        fases: Array.isArray(g.fases) ? g.fases : [],
        agentes: Array.isArray(g.agentes) ? g.agentes : [],
      })),
    })),
  };
}

export const buscarAgentes = (todos: boolean) => apiGet<unknown>(urlAgentes(todos)).then(normalizarAgentes);

/**
 * A cada 2 s. O TanStack Query ja pausa o intervalo com a aba escondida
 * (refetchIntervalInBackground falso); keepPreviousData evita esqueleto ao trocar "so ativos"/"todos".
 */
export const useAgentes = (todos: boolean) =>
  useQuery({
    queryKey: chaveAgentes(todos),
    queryFn: () => buscarAgentes(todos),
    refetchInterval: () => (typeof document !== 'undefined' && document.hidden ? false : 2000),
    refetchIntervalInBackground: false,
    placeholderData: keepPreviousData,
  });
