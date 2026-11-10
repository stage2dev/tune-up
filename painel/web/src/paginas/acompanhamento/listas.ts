// Logica da tela de Acompanhamento: ordem, filtro e contagem das listas de trabalho.
// As areas vem do servidor (campo "area" de cada lista e, se houver, "areas" com os titulos): nada fixo aqui.
import type { AreaAcompanhamento, ItemLista, ListaAcompanhamento } from '../../api/tipos';

export const TODAS = 'todas';

function tempo(t: string): number {
  const n = Date.parse(t);
  return Number.isNaN(n) ? 0 : n;
}

function capitalizar(id: string): string {
  const t = id.replace(/[_-]+/g, ' ').trim();
  return t ? t.charAt(0).toUpperCase() + t.slice(1) : 'Geral';
}

/** Areas na ordem do servidor; as que so aparecem nas listas entram depois, na ordem em que surgem. */
export function areasDe(listas: ListaAcompanhamento[], areas?: AreaAcompanhamento[]): AreaAcompanhamento[] {
  const out: AreaAcompanhamento[] = [];
  const vistas = new Set<string>();
  const por = (id: string, titulo?: string) => {
    if (vistas.has(id)) return;
    vistas.add(id);
    out.push({ id, titulo: titulo || capitalizar(id) });
  };
  for (const a of areas ?? []) if (a && typeof a.id === 'string') por(a.id, a.titulo);
  for (const l of listas) por(l.area || 'geral');
  return out;
}

/** Ordem das areas, depois a lista mais mexida primeiro. */
export function ordenarListas(listas: ListaAcompanhamento[], ordem: AreaAcompanhamento[] = areasDe(listas)): ListaAcompanhamento[] {
  const pos = (a: string) => {
    const i = ordem.findIndex((x) => x.id === (a || 'geral'));
    return i < 0 ? ordem.length : i;
  };
  return [...listas].sort((a, b) => pos(a.area) - pos(b.area) || tempo(b.atualizado_em) - tempo(a.atualizado_em));
}

export function filtrarListas(listas: ListaAcompanhamento[], area: string, mostrarFechadas: boolean, ordem?: AreaAcompanhamento[]): ListaAcompanhamento[] {
  return ordenarListas(listas.filter((l) => (area === TODAS || (l.area || 'geral') === area) && (mostrarFechadas || l.aberta)), ordem);
}

/** Quantas listas ha por area (respeitando "mostrar fechadas"), para os contadores dos filtros. */
export function contarPorArea(listas: ListaAcompanhamento[], mostrarFechadas: boolean): Record<string, number> {
  const out: Record<string, number> = { [TODAS]: 0 };
  for (const l of listas) {
    if (!mostrarFechadas && !l.aberta) continue;
    const a = l.area || 'geral';
    out[a] = (out[a] ?? 0) + 1;
    out[TODAS] += 1;
  }
  return out;
}

export function resumoItens(itens: ItemLista[]): { total: number; feitos: number; fazendo: number; aFazer: number } {
  return {
    total: itens.length,
    feitos: itens.filter((i) => i.status === 'done').length,
    fazendo: itens.filter((i) => i.status === 'doing').length,
    aFazer: itens.filter((i) => i.status === 'todo').length,
  };
}

/** Itens em andamento primeiro, depois a fazer, feitos, e por fim deixados de lado. */
const ORDEM_STATUS: Record<ItemLista['status'], number> = { doing: 0, todo: 1, done: 2, dropped: 3 };
export function ordenarItens(itens: ItemLista[]): ItemLista[] {
  return [...itens].sort((a, b) => ORDEM_STATUS[a.status] - ORDEM_STATUS[b.status] || tempo(b.atualizado_em) - tempo(a.atualizado_em));
}
