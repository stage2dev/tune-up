// Funcoes puras da tela Agentes (testadas em logica.test.ts).
import type { AgenteVivo, GrupoAgentes, SessaoClaude } from '../../api/agentes';

// ---------- modelo ----------
export type Familia = 'opus' | 'sonnet' | 'haiku' | 'outro';

/** Familia pelo texto do modelo (curto ou id completo). Sem lista de versoes. */
export function familiaModelo(modelo: string | null | undefined): Familia {
  const t = (modelo ?? '').toLowerCase();
  if (t.includes('opus')) return 'opus';
  if (t.includes('sonnet')) return 'sonnet';
  if (t.includes('haiku')) return 'haiku';
  return 'outro';
}

/** Uma cor fixa por familia, sempre por token (funciona no claro e no escuro). */
export const COR_FAMILIA: Record<Familia, string> = {
  opus: 'var(--color-purple)',
  sonnet: 'var(--color-accent)',
  haiku: 'var(--color-warning)',
  outro: 'var(--color-text-tertiary)',
};

export const corModelo = (modelo: string | null | undefined) => COR_FAMILIA[familiaModelo(modelo)];

/** Texto curto do chip: "Opus", "Sonnet"... ou o proprio nome curto; sem modelo, "?". */
export function rotuloModelo(modelo: string | null | undefined): string {
  const f = familiaModelo(modelo);
  if (f !== 'outro') return f[0].toUpperCase() + f.slice(1);
  const t = (modelo ?? '').trim();
  return t ? (t.length > 18 ? `${t.slice(0, 17)}…` : t) : '?';
}

// ---------- esforco ----------
export const DEGRAUS = ['low', 'medium', 'high', 'xhigh', 'max'] as const;
const NOME_DEGRAU = ['não informado', 'baixo', 'médio', 'alto', 'muito alto', 'máximo'];

/** 0 = nao informado; 1..5 = low..max. */
export function degrauEsforco(esforco: string | null | undefined): number {
  if (!esforco) return 0;
  const i = (DEGRAUS as readonly string[]).indexOf(esforco.toLowerCase().trim());
  return i < 0 ? 0 : i + 1;
}

export const rotuloEsforco = (esforco: string | null | undefined) => NOME_DEGRAU[degrauEsforco(esforco)];

// ---------- tempo ----------
export function paraMs(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  return Number.isNaN(t) ? null : t;
}

/** Segundos em texto curto: "45 s", "3 min 05 s", "1 h 02 min". */
export function formatarDuracao(segundos: number | null | undefined): string {
  if (segundos === null || segundos === undefined || !Number.isFinite(segundos)) return '—';
  const s = Math.max(0, Math.floor(segundos));
  if (s < 60) return `${s} s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} min ${String(s % 60).padStart(2, '0')} s`;
  const h = Math.floor(m / 60);
  if (h < 48) return `${h} h ${String(m % 60).padStart(2, '0')} min`;
  return `${Math.floor(h / 24)} d ${h % 24} h`;
}

/** Cronometro do agente: ao vivo se rodando, senao a duracao final. */
export function duracaoAgente(a: Pick<AgenteVivo, 'estado' | 'iniciado_em' | 'duracao_s' | 'ultima_atividade'>, agora: number): number | null {
  const ini = paraMs(a.iniciado_em);
  if (a.estado === 'rodando') return ini === null ? a.duracao_s : (agora - ini) / 1000;
  if (a.duracao_s !== null && a.duracao_s !== undefined) return a.duracao_s;
  const fim = paraMs(a.ultima_atividade);
  return ini !== null && fim !== null ? (fim - ini) / 1000 : null;
}

export function tempoDesde(iso: string | null | undefined, agora: number): string {
  const t = paraMs(iso);
  return t === null ? '—' : formatarDuracao((agora - t) / 1000);
}

// ---------- arvore ----------
export interface No {
  agente: AgenteVivo;
  filhos: No[];
}

const porInicio = (a: AgenteVivo, b: AgenteVivo) => (paraMs(a.iniciado_em) ?? 0) - (paraMs(b.iniciado_em) ?? 0) || a.id.localeCompare(b.id);

/**
 * Monta a arvore por pai_id. Pai que nao esta na lista (ex.: e a propria sessao, ou foi cortado)
 * vira raiz. Ciclos sao quebrados: cada agente aparece uma vez so.
 */
export function montarArvore(agentes: AgenteVivo[]): No[] {
  const ids = new Set(agentes.map((a) => a.id));
  const filhosDe = new Map<string, AgenteVivo[]>();
  const raizes: AgenteVivo[] = [];
  for (const a of agentes) {
    if (a.pai_id && a.pai_id !== a.id && ids.has(a.pai_id)) {
      const l = filhosDe.get(a.pai_id) ?? [];
      l.push(a);
      filhosDe.set(a.pai_id, l);
    } else raizes.push(a);
  }
  const vistos = new Set<string>();
  const montar = (a: AgenteVivo): No => {
    vistos.add(a.id);
    const filhos = (filhosDe.get(a.id) ?? []).filter((f) => !vistos.has(f.id)).sort(porInicio).map(montar);
    return { agente: a, filhos };
  };
  const arvore = raizes.sort(porInicio).map(montar);
  // Sobrou alguem (ciclo puro, sem raiz)? Entra como raiz.
  for (const a of [...agentes].sort(porInicio)) if (!vistos.has(a.id)) arvore.push(montar(a));
  return arvore;
}

/** Agentes de um workflow repartidos pelas fases (na ordem do grupo); fase desconhecida vai para "Sem fase". */
export function porFase(g: Pick<GrupoAgentes, 'fases' | 'agentes'>): { fase: string; agentes: AgenteVivo[] }[] {
  const colunas = g.fases.map((fase) => ({ fase, agentes: [] as AgenteVivo[] }));
  const idx = new Map(g.fases.map((f, i) => [f, i]));
  const sem: AgenteVivo[] = [];
  for (const a of g.agentes) {
    const i = a.fase !== null && a.fase !== undefined ? idx.get(a.fase) : undefined;
    if (i === undefined) sem.push(a);
    else colunas[i].agentes.push(a);
  }
  if (sem.length) colunas.push({ fase: 'Sem fase', agentes: sem });
  return colunas;
}

export const contarAtivos = (agentes: AgenteVivo[]) => agentes.filter((a) => a.estado === 'rodando').length;

// ---------- resumo ----------
export interface Fatia {
  chave: string;
  rotulo: string;
  valor: number;
  cor: string;
}

export interface Resumo {
  sessoesRodando: number;
  sessoesTotal: number;
  agentesAtivos: number;
  porModelo: Fatia[];
  porEsforco: Fatia[];
}

export const sessaoAtiva = (s: Pick<SessaoClaude, 'estado'>) => s.estado === 'rodando' || s.estado === 'precisa_de_voce';

// Cor do degrau: mesma tinta, mais forte quanto maior o esforco.
export const corDegrau = (d: number) =>
  d === 0 ? 'var(--color-bg-tertiary)' : `color-mix(in srgb, var(--color-text) ${20 + d * 15}%, transparent)`;

/** Conta as instancias trabalhando agora: sessoes ativas + agentes rodando. */
export function resumir(sessoes: SessaoClaude[]): Resumo {
  const modelos = new Map<Familia, number>();
  const outros = new Map<string, number>();
  const esforcos = new Array(DEGRAUS.length + 1).fill(0) as number[];
  let agentesAtivos = 0;
  const contar = (modelo: string | null, esforco: string | null) => {
    const f = familiaModelo(modelo);
    if (f === 'outro') {
      const nome = (modelo ?? '').trim() || 'não informado';
      outros.set(nome, (outros.get(nome) ?? 0) + 1);
    } else modelos.set(f, (modelos.get(f) ?? 0) + 1);
    esforcos[degrauEsforco(esforco)] += 1;
  };
  for (const s of sessoes) {
    if (sessaoAtiva(s)) contar(s.modelo, s.esforco);
    for (const g of s.grupos)
      for (const a of g.agentes)
        if (a.estado === 'rodando') {
          agentesAtivos += 1;
          contar(a.modelo, a.esforco);
        }
  }
  const ordem: Familia[] = ['opus', 'sonnet', 'haiku'];
  return {
    sessoesRodando: sessoes.filter(sessaoAtiva).length,
    sessoesTotal: sessoes.length,
    agentesAtivos,
    porModelo: [
      ...ordem
        .filter((f) => modelos.get(f))
        .map((f) => ({ chave: f as string, rotulo: rotuloModelo(f), valor: modelos.get(f) ?? 0, cor: COR_FAMILIA[f] })),
      ...[...outros.entries()].map(([nome, valor]) => ({ chave: `outro:${nome}`, rotulo: nome, valor, cor: COR_FAMILIA.outro })),
    ],
    porEsforco: [1, 2, 3, 4, 5, 0]
      .filter((d) => esforcos[d] > 0)
      .map((d) => ({ chave: String(d), rotulo: NOME_DEGRAU[d], valor: esforcos[d], cor: corDegrau(d) })),
  };
}

// ---------- textos ----------
export const TIPO_SESSAO: Record<string, string> = { interativa: 'No terminal', segundo_plano: 'Segundo plano' };

/** Selo da sessao: o componente Selo ja conhece rodando/precisa_de_voce/terminou/parada; ocioso nao. */
export function seloSessao(estado: string): { rotulo?: string; tom?: 'neutro' } {
  return estado === 'ocioso' ? { rotulo: 'Ociosa', tom: 'neutro' } : {};
}

export const plural = (n: number, um: string, varios: string) => `${n} ${n === 1 ? um : varios}`;
