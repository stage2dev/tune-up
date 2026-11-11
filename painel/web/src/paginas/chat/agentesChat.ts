// Funcoes puras do painel "Quem esta trabalhando" e da frase "trabalhando…" (testadas em agentesChat.test.ts).
import type { RespostaAgentes, SessaoClaude } from '../../api/agentes';
import type { EventoExecucao } from '../../api/tipos';
import { contarAtivos, montarArvore, porFase, type No } from '../agentes/logica';

/** A sessao da conversa: a que casa com o id da execucao; o servidor ja filtra por ?sessao=. */
export function sessaoDaConversa(r: RespostaAgentes | undefined, id: string): SessaoClaude | null {
  const ss = r?.sessoes ?? [];
  return ss.find((s) => s.id === id || s.execucao_id === id || s.sessao_id === id) ?? ss[0] ?? null;
}

export interface BlocoAgentes {
  chave: string;
  titulo: string | null; // nome do workflow; null = agentes chamados direto
  fases: { fase: string | null; arvore: No[] }[];
}

export interface ItensPainel {
  blocos: BlocoAgentes[];
  total: number;
  ativos: number;
}

/** Agentes da sessao agrupados: direto vira uma arvore; workflow vira colunas por fase. */
export function itensDoPainel(s: SessaoClaude | null): ItensPainel {
  if (!s) return { blocos: [], total: 0, ativos: 0 };
  const blocos: BlocoAgentes[] = [];
  let total = 0;
  let ativos = 0;
  for (const g of s.grupos) {
    if (g.agentes.length === 0) continue;
    total += g.agentes.length;
    ativos += contarAtivos(g.agentes);
    if (g.tipo === 'workflow') {
      blocos.push({
        chave: `w:${g.id}`,
        titulo: g.nome || 'Fluxo',
        fases: porFase(g)
          .filter((c) => c.agentes.length > 0)
          .map((c) => ({ fase: c.fase, arvore: montarArvore(c.agentes) })),
      });
    } else blocos.push({ chave: `d:${g.id}`, titulo: null, fases: [{ fase: null, arvore: montarArvore(g.agentes) }] });
  }
  return { blocos, total, ativos };
}

const FERRAMENTAS: [RegExp, string][] = [
  [/^(Read|Glob|Grep|LS|NotebookRead)$/, 'lendo arquivos'],
  [/^(Edit|Write|MultiEdit|NotebookEdit)$/, 'mexendo nos arquivos'],
  [/^Bash$/, 'rodando um comando'],
  [/^(WebFetch|WebSearch)$/, 'pesquisando na internet'],
  [/^(Task|Agent)$/, 'chamando um ajudante'],
  [/^TodoWrite$/, 'organizando as tarefas'],
  [/^mcp__/, 'consultando um serviço'],
];

/** "trabalhando… lendo arquivos" / "trabalhando… 2 agentes ajudando" / "trabalhando…". */
export function fraseTrabalhando(eventos: EventoExecucao[], agentesAtivos: number): string {
  if (agentesAtivos > 0) return `trabalhando… ${agentesAtivos} ${agentesAtivos === 1 ? 'agente ajudando' : 'agentes ajudando'}`;
  for (let i = eventos.length - 1; i >= 0; i--) {
    const ev = eventos[i];
    if (ev.tipo === 'assistente' || ev.tipo === 'usuario') break; // so a atividade depois da ultima fala
    if (ev.tipo === 'subagente') return 'trabalhando… chamando um ajudante';
    if (ev.tipo === 'ferramenta' && ev.ferramenta) {
      const achou = FERRAMENTAS.find(([re]) => re.test(ev.ferramenta ?? ''));
      if (achou) return `trabalhando… ${achou[1]}`;
      return 'trabalhando…';
    }
  }
  return 'trabalhando…';
}
