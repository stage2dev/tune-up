// Tipos e busca de GET /api/custo (tokens e US$ estimados por sessao do Claude).
// Contrato fixo: ?sessao=<uuid> repetido, de 1 a 60 UUIDs completos. A tela de Agentes nunca depende dele.
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { apiGet } from './cliente';

export const MAX_SESSOES_CUSTO = 60;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

export interface TokensCusto {
  entrada: number | null;
  saida: number | null;
  cache_escrita: number | null;
  cache_leitura: number | null;
  total: number | null;
}

export interface ModeloCusto {
  modelo: string;
  tokens: number | null;
  usd: number | null;
  pct: number | null;
}

export interface CustoSessao {
  sessao_id: string;
  encontrada: boolean;
  parcial: boolean;
  tokens: TokensCusto | null;
  contexto_maximo: number | null;
  subagentes: number | null;
  usd: number | null;
  usd_incompleto: boolean;
  modelos: ModeloCusto[];
}

export type MapaCusto = ReadonlyMap<string, CustoSessao>;

const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);

/** Ids que o servidor aceita (UUID completo minusculo), sem repetir, na ordem da tela; no maximo 60. */
export function idsParaCusto(ids: readonly string[]): { enviados: string[]; chave: string[] } {
  const enviados = [...new Set(ids.filter((i) => UUID.test(i)))].slice(0, MAX_SESSOES_CUSTO);
  return { enviados, chave: [...enviados].sort() };
}

export function urlCusto(ids: readonly string[]): string {
  const q = new URLSearchParams();
  for (const i of ids) q.append('sessao', i);
  return `/api/custo?${q.toString()}`;
}

/** Normaliza o que chegou: campo que falta ou veio torto vira null/false, nunca quebra o cartao. */
export function normalizarCusto(bruto: unknown): Map<string, CustoSessao> {
  const mapa = new Map<string, CustoSessao>();
  const r = (bruto && typeof bruto === 'object' ? bruto : {}) as { sessoes?: unknown };
  if (!Array.isArray(r.sessoes)) return mapa;
  for (const item of r.sessoes) {
    if (!item || typeof item !== 'object') continue;
    const s = item as Record<string, unknown>;
    if (typeof s.sessao_id !== 'string' || !s.sessao_id) continue;
    const t = s.tokens && typeof s.tokens === 'object' ? (s.tokens as Record<string, unknown>) : null;
    mapa.set(s.sessao_id, {
      sessao_id: s.sessao_id,
      encontrada: s.encontrada === true,
      parcial: s.parcial === true,
      tokens: t
        ? { entrada: num(t.entrada), saida: num(t.saida), cache_escrita: num(t.cache_escrita), cache_leitura: num(t.cache_leitura), total: num(t.total) }
        : null,
      contexto_maximo: num(s.contexto_maximo),
      subagentes: num(s.subagentes),
      usd: num(s.usd),
      usd_incompleto: s.usd_incompleto === true,
      modelos: (Array.isArray(s.modelos) ? s.modelos : [])
        .filter((m): m is Record<string, unknown> => !!m && typeof m === 'object' && typeof (m as Record<string, unknown>).modelo === 'string')
        .map((m) => ({ modelo: m.modelo as string, tokens: num(m.tokens), usd: num(m.usd), pct: num(m.pct) })),
    });
  }
  return mapa;
}

/**
 * A cada 30 s (o TanStack Query pausa com a aba escondida). A chave e a lista ordenada: reordenar a tela nao
 * refaz o pedido; keepPreviousData mantem os custos ja lidos quando entra outra sessao. Sem timeout curto:
 * o primeiro calculo pode levar alguns segundos.
 */
export function useCusto(idsDaTela: readonly string[]) {
  const { enviados, chave } = idsParaCusto(idsDaTela);
  const q = useQuery({
    queryKey: ['custo', ...chave] as const,
    enabled: chave.length > 0,
    queryFn: () => apiGet<unknown>(urlCusto(chave)).then(normalizarCusto),
    refetchInterval: () => (typeof document !== 'undefined' && document.hidden ? false : 30000),
    refetchIntervalInBackground: false,
    staleTime: 15000,
    placeholderData: keepPreviousData,
  });
  return { mapa: q.data, enviados: new Set(enviados), erro: q.isError, buscando: q.isFetching || (chave.length > 0 && q.isPending) };
}

export type EstadoCusto = { tipo: 'calculando' } | { tipo: 'erro' } | { tipo: 'dados'; custo: CustoSessao };

export interface ContextoCusto {
  mapa: MapaCusto | undefined;
  enviados: ReadonlySet<string>;
  erro: boolean;
  buscando: boolean;
}

/** O que o cartao de uma sessao mostra. Dado ja lido ganha de erro; ausente + buscando = calculando. */
export function estadoDoCusto(sessaoId: string, c: ContextoCusto): EstadoCusto {
  if (!c.enviados.has(sessaoId)) return { tipo: 'erro' };
  const custo = c.mapa?.get(sessaoId);
  if (custo) return { tipo: 'dados', custo };
  if (c.buscando) return { tipo: 'calculando' };
  return { tipo: 'erro' };
}
