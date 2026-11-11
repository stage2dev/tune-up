import { describe, expect, it } from 'vitest';
import type { AgenteVivo, RespostaAgentes, SessaoClaude } from '../../api/agentes';
import type { EventoExecucao } from '../../api/tipos';
import { fraseTrabalhando, itensDoPainel, sessaoDaConversa } from './agentesChat';

const ag = (id: string, extra: Partial<AgenteVivo> = {}): AgenteVivo => ({
  id,
  tipo_agente: 'Explore',
  descricao: id,
  fase: null,
  modelo: 'haiku',
  modelo_id: null,
  esforco: null,
  estado: 'terminou',
  profundidade: 1,
  pai_id: null,
  iniciado_em: '2026-11-10T10:00:00Z',
  ultima_atividade: null,
  duracao_s: 10,
  ferramentas: 1,
  ultima_acao: null,
  ...extra,
});

const sessao = (id: string, grupos: SessaoClaude['grupos'] = []): SessaoClaude => ({
  id,
  sessao_id: `${id}-uuid`,
  nome: id,
  tipo: 'segundo_plano',
  estado: 'rodando',
  modelo: 'opus',
  esforco: 'high',
  iniciado_em: null,
  ultima_atividade: null,
  execucao_id: id,
  agentes_ativos: 0,
  agentes_total: 0,
  grupos,
});

describe('sessaoDaConversa', () => {
  it('acha pelo id; sem casar, a primeira; sem dados, null', () => {
    const r: RespostaAgentes = { gerado_em: '', avisos: [], sessoes: [sessao('aaa'), sessao('bbb')] };
    expect(sessaoDaConversa(r, 'bbb')?.id).toBe('bbb');
    expect(sessaoDaConversa(r, 'zzz')?.id).toBe('aaa');
    expect(sessaoDaConversa(undefined, 'x')).toBeNull();
  });
});

describe('itensDoPainel', () => {
  it('sem sessao ou sem agentes = vazio', () => {
    expect(itensDoPainel(null)).toEqual({ blocos: [], total: 0, ativos: 0 });
    expect(itensDoPainel(sessao('a', [{ tipo: 'direto', id: 'd', nome: '', fases: [], agentes: [] }])).blocos).toEqual([]);
  });
  it('direto vira arvore; workflow vira fases; conta ativos', () => {
    const s = sessao('a', [
      { tipo: 'direto', id: 'd', nome: '', fases: [], agentes: [ag('p', { estado: 'rodando' }), ag('f', { pai_id: 'p' })] },
      { tipo: 'workflow', id: 'w', nome: 'Revisão', fases: ['ler', 'revisar', 'vazia'], agentes: [ag('r1', { fase: 'revisar', estado: 'rodando' }), ag('l1', { fase: 'ler' })] },
    ]);
    const it = itensDoPainel(s);
    expect(it.total).toBe(4);
    expect(it.ativos).toBe(2);
    expect(it.blocos[0].titulo).toBeNull();
    expect(it.blocos[0].fases[0].arvore.map((n) => [n.agente.id, n.filhos.map((f) => f.agente.id)])).toEqual([['p', ['f']]]);
    expect(it.blocos[1].titulo).toBe('Revisão');
    expect(it.blocos[1].fases.map((f) => f.fase)).toEqual(['ler', 'revisar']); // fase vazia some
  });
});

const ev = (n: number, tipo: EventoExecucao['tipo'], ferramenta?: string): EventoExecucao => ({ n, ts: '', tipo, texto: '', ferramenta });

describe('fraseTrabalhando', () => {
  it('agentes ativos ganham', () => {
    expect(fraseTrabalhando([ev(1, 'ferramenta', 'Read')], 2)).toBe('trabalhando… 2 agentes ajudando');
    expect(fraseTrabalhando([], 1)).toBe('trabalhando… 1 agente ajudando');
  });
  it('ultima ferramenta em palavras simples', () => {
    expect(fraseTrabalhando([ev(1, 'ferramenta', 'Edit'), ev(2, 'ferramenta', 'Grep')], 0)).toBe('trabalhando… lendo arquivos');
    expect(fraseTrabalhando([ev(1, 'ferramenta', 'mcp__x__y')], 0)).toBe('trabalhando… consultando um serviço');
    expect(fraseTrabalhando([ev(1, 'ferramenta', 'Bash'), ev(2, 'resultado')], 0)).toBe('trabalhando… rodando um comando');
  });
  it('sem atividade depois da ultima fala = so trabalhando', () => {
    expect(fraseTrabalhando([ev(1, 'ferramenta', 'Read'), ev(2, 'assistente')], 0)).toBe('trabalhando…');
    expect(fraseTrabalhando([ev(1, 'ferramenta', 'Desconhecida')], 0)).toBe('trabalhando…');
  });
});
