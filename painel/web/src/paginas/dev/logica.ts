// Funcoes puras das telas de desenvolvimento (sem React), testadas em logica.test.ts.
import { apiPost, ErroApi } from '../../api/cliente';
import type { Execucao, EventoExecucao } from '../../api/tipos';
import type { Estado, Fase, ItemRevisado, Parte, Pendencia, StatusParte } from './tipos';

// ---------------------------------------------------------------- estado
/** /api/estado pode vir como {erro, avisos} com status 200. */
export function lerEstado(dado: unknown): { estado?: Estado; erro?: string } {
  const d = (dado ?? {}) as Record<string, unknown>;
  if (typeof d.erro === 'string') return { erro: d.erro };
  if (!d.resumo || !Array.isArray(d.fases)) return { erro: 'O painel mandou um estado que não entendi.' };
  return { estado: d as unknown as Estado };
}

const num = (f: Fase): number => {
  const n = parseInt(f.numero, 10);
  return Number.isNaN(n) ? -1 : n;
};

/** Mais novas primeiro. */
export function ordenarFases(fases: Fase[]): Fase[] {
  return [...fases].sort((a, b) => num(b) - num(a) || b.numero.localeCompare(a.numero));
}

export function faseFechada(f: Fase): boolean {
  return f.acompanhada && f.partes.length > 0 && f.partes.every((p) => p.status === 'fechada');
}

export function contarPartes(f: Fase): { fechadas: number; total: number } {
  return { fechadas: f.partes.filter((p) => p.status === 'fechada').length, total: f.partes.length };
}

const limpar = (s: string): string =>
  s
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .trim();

/** Busca por numero ("187", "fase 187") ou por pedaco do nome. */
export function casaBusca(f: Fase, busca: string): boolean {
  const q = limpar(busca).replace(/^fase\s*/, '');
  if (!q) return true;
  if (/^\d+$/.test(q) && f.numero.replace(/^0+/, '').startsWith(q.replace(/^0+/, ''))) return true;
  return limpar(`${f.numero} ${f.titulo ?? ''} ${f.slug}`).includes(q);
}

export interface Grupos {
  abertas: Fase[];
  fechadas: Fase[];
  semAcompanhamento: Fase[];
}

export function agrupar(fases: Fase[], busca: string): Grupos {
  const g: Grupos = { abertas: [], fechadas: [], semAcompanhamento: [] };
  for (const f of ordenarFases(fases)) {
    if (!casaBusca(f, busca)) continue;
    if (!f.acompanhada) g.semAcompanhamento.push(f);
    else if (faseFechada(f)) g.fechadas.push(f);
    else g.abertas.push(f);
  }
  return g;
}

export const SELO_PARTE: Record<StatusParte, { rotulo: string; tom: 'ok' | 'atencao' | 'destaque' | 'neutro' }> = {
  fechada: { rotulo: 'Fechada', tom: 'ok' },
  precisa_de_voce: { rotulo: 'Precisa de você', tom: 'atencao' },
  rodando: { rotulo: 'Rodando', tom: 'destaque' },
  pendente: { rotulo: 'Ainda não feita', tom: 'neutro' },
};

export function textoVolta(v: { volta: number | null; critico: number; alto: number }): string {
  const nome = v.volta === null ? 'Revisão' : `Volta ${v.volta}`;
  const achados: string[] = [];
  if (v.critico) achados.push(`${v.critico} crítico${v.critico > 1 ? 's' : ''}`);
  if (v.alto) achados.push(`${v.alto} alto${v.alto > 1 ? 's' : ''}`);
  return `${nome}: ${achados.length ? achados.join(' e ') : 'sem achado'}`;
}

export function itemTemAchado(i: ItemRevisado): boolean {
  return i.voltas.some((v) => v.critico > 0 || v.alto > 0);
}

export function parteAberta(p: Parte): boolean {
  return p.status !== 'fechada';
}

// ---------------------------------------------------------------- execucoes
export function formatarDuracao(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000));
  if (s < 60) return `${s} s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} min ${String(s % 60).padStart(2, '0')} s`;
  const h = Math.floor(m / 60);
  return `${h} h ${String(m % 60).padStart(2, '0')} min`;
}

export function emAndamento(e: Pick<Execucao, 'estado'>): boolean {
  return e.estado === 'rodando' || e.estado === 'precisa_de_voce';
}

export function paraMs(iso: string | undefined): number | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  return Number.isNaN(t) ? null : t;
}

/** Tempo desde o inicio ate `fimMs` (agora, ou o ultimo sinal de vida quando ja acabou). */
export function tempoDecorrido(iniciadaEm: string, fimMs: number): string {
  const ini = paraMs(iniciadaEm);
  return ini === null ? '—' : formatarDuracao(fimMs - ini);
}

export function ultimoSinal(eventos: EventoExecucao[]): number | null {
  for (let i = eventos.length - 1; i >= 0; i--) {
    const t = paraMs(eventos[i].ts);
    if (t !== null) return t;
  }
  return null;
}

export function horaDoEvento(ts: string): string {
  const t = paraMs(ts);
  return t === null ? '' : new Date(t).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

/** Perto do fim da rolagem = acompanha; quem subiu fica onde esta. */
export function estaNoFim(scrollHeight: number, scrollTop: number, clientHeight: number, folga = 48): boolean {
  return scrollHeight - scrollTop - clientHeight <= folga;
}

// ---------------------------------------------------------------- Inicio
export interface ItemPrecisa {
  chave: string;
  origem: 'estado' | 'execucao';
  titulo: string;
  texto: string;
  para?: string; // rota interna
}

export function juntarPrecisa(pendencias: Pendencia[], execucoes: Execucao[]): ItemPrecisa[] {
  const deExec: ItemPrecisa[] = execucoes
    .filter((e) => e.estado === 'precisa_de_voce')
    .map((e) => ({
      chave: `exec-${e.id}`,
      origem: 'execucao',
      titulo: e.titulo,
      texto: 'A sessão do Claude está esperando uma resposta sua no terminal.',
      para: `/execucoes/${e.id}`,
    }));
  const deEstado: ItemPrecisa[] = pendencias.map((p, i) => ({
    chave: `est-${p.fase}-${p.parte ?? ''}-${i}`,
    origem: 'estado',
    titulo: `Fase ${p.fase}${p.parte ? ` · Parte ${p.parte}` : ''} · ${p.tipo === 'pergunta' ? 'pergunta aberta' : 'espera por você'}`,
    texto: p.texto,
    para: '/fases',
  }));
  return [...deExec, ...deEstado];
}

// ---------------------------------------------------------------- iniciar execucao
export interface PedidoInicio {
  acao: string;
  params: Record<string, string>;
}

export const ACAO_RODAR_PARTE = 'dev.rodar-parte';

export function pedidoRodarParte(fase: string, parte: string): PedidoInicio {
  return { acao: ACAO_RODAR_PARTE, params: { fase, parte } };
}

/** POST /api/execucoes (o token e o 403 velho sao tratados em api/cliente). */
export function iniciar(pedido: PedidoInicio): Promise<Execucao> {
  return apiPost<{ execucao: Execucao }>('/api/execucoes', pedido).then((r) => r.execucao);
}

export type ResultadoErro = { tipo: 'conflito'; texto: string; execucaoId: string } | { tipo: 'erro'; texto: string };

export function traduzirErroInicio(e: unknown): ResultadoErro {
  if (e instanceof ErroApi) {
    if (e.status === 409 && e.execucaoId) return { tipo: 'conflito', texto: e.message, execucaoId: e.execucaoId };
    return { tipo: 'erro', texto: e.message };
  }
  return { tipo: 'erro', texto: 'Algo deu errado. Tente de novo.' };
}
