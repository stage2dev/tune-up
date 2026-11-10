import { describe, expect, it } from 'vitest';
import type { SessaoClaude } from '../../api/agentes';
import { agente } from './exemplo';
import { normalizarAgentes, urlAgentes } from '../../api/agentes';
import {
  corModelo, degrauEsforco, duracaoAgente, familiaModelo, formatarDuracao, montarArvore, porFase, resumir, rotuloEsforco, rotuloModelo,
} from './logica';


describe('modelo', () => {
  it('familia pelo texto, curto ou id completo, sem lista de versoes', () => {
    expect(familiaModelo('opus')).toBe('opus');
    expect(familiaModelo('claude-opus-9-1[1m]')).toBe('opus');
    expect(familiaModelo('Sonnet')).toBe('sonnet');
    expect(familiaModelo('claude-haiku-7')).toBe('haiku');
    expect(familiaModelo('gpt-x')).toBe('outro');
    expect(familiaModelo(null)).toBe('outro');
  });
  it('cor fixa por familia e neutra para desconhecido', () => {
    expect(corModelo('opus')).toBe(corModelo('claude-opus-1'));
    expect(new Set([corModelo('opus'), corModelo('sonnet'), corModelo('haiku'), corModelo('xyz')]).size).toBe(4);
    expect(corModelo('xyz')).toBe(corModelo(undefined));
  });
  it('rotulo do chip', () => {
    expect(rotuloModelo('claude-opus-5')).toBe('Opus');
    expect(rotuloModelo('modelo-local')).toBe('modelo-local');
    expect(rotuloModelo(null)).toBe('?');
  });
});

describe('esforco', () => {
  it('5 degraus e 0 para nulo ou desconhecido', () => {
    expect(['low', 'medium', 'high', 'xhigh', 'max'].map(degrauEsforco)).toEqual([1, 2, 3, 4, 5]);
    expect(degrauEsforco(null)).toBe(0);
    expect(degrauEsforco('turbo')).toBe(0);
    expect(degrauEsforco('HIGH')).toBe(3);
  });
  it('rotulo em portugues', () => {
    expect(rotuloEsforco('xhigh')).toBe('muito alto');
    expect(rotuloEsforco(null)).toBe('não informado');
  });
});

describe('duracao', () => {
  it('formata segundos', () => {
    expect(formatarDuracao(45)).toBe('45 s');
    expect(formatarDuracao(185)).toBe('3 min 05 s');
    expect(formatarDuracao(3720)).toBe('1 h 02 min');
    expect(formatarDuracao(-5)).toBe('0 s');
    expect(formatarDuracao(null)).toBe('—');
    expect(formatarDuracao(3 * 86400 + 7200)).toBe('3 d 2 h');
  });
  it('cronometro ao vivo se rodando, final se terminou', () => {
    const agora = Date.parse('2026-11-10T10:02:00Z');
    expect(duracaoAgente(agente('a'), agora)).toBe(120);
    expect(duracaoAgente(agente('b', { estado: 'terminou', duracao_s: 30 }), agora)).toBe(30);
    expect(duracaoAgente(agente('c', { estado: 'terminou' }), agora)).toBe(60);
  });
});

describe('arvore por pai_id', () => {
  it('aninha filhos, pai ausente vira raiz, ordem por inicio', () => {
    const arv = montarArvore([
      agente('neto', { pai_id: 'filho', iniciado_em: '2026-11-10T10:03:00Z' }),
      agente('filho', { pai_id: 'raiz', iniciado_em: '2026-11-10T10:02:00Z' }),
      agente('raiz', { pai_id: 'sessao-x', iniciado_em: '2026-11-10T10:01:00Z' }),
      agente('solto', { iniciado_em: '2026-11-10T10:00:00Z' }),
    ]);
    expect(arv.map((n) => n.agente.id)).toEqual(['solto', 'raiz']);
    expect(arv[1].filhos[0].agente.id).toBe('filho');
    expect(arv[1].filhos[0].filhos[0].agente.id).toBe('neto');
  });
  it('ciclo nao trava e ninguem some', () => {
    const arv = montarArvore([agente('a', { pai_id: 'b' }), agente('b', { pai_id: 'a' })]);
    const ids: string[] = [];
    const andar = (ns: typeof arv) => ns.forEach((n) => { ids.push(n.agente.id); andar(n.filhos); });
    andar(arv);
    expect(ids.sort()).toEqual(['a', 'b']);
  });
  it('reparte workflow por fase e junta o que nao tem fase', () => {
    const cols = porFase({ fases: ['Plano', 'Fazer'], agentes: [agente('1', { fase: 'Fazer' }), agente('2', { fase: 'Plano' }), agente('3')] });
    expect(cols.map((c) => [c.fase, c.agentes.map((a) => a.id)])).toEqual([['Plano', ['2']], ['Fazer', ['1']], ['Sem fase', ['3']]]);
  });
});

describe('resumo', () => {
  it('conta sessoes ativas e agentes rodando por modelo e esforco', () => {
    const s: SessaoClaude = {
      id: 's1', sessao_id: 's1', nome: 'x', tipo: 'interativa', estado: 'rodando', modelo: 'opus', esforco: 'xhigh',
      iniciado_em: null, ultima_atividade: null, execucao_id: null, agentes_ativos: 1, agentes_total: 2,
      grupos: [{ tipo: 'direto', id: 'd', nome: '', fases: [], agentes: [agente('a'), agente('b', { estado: 'terminou', modelo: 'haiku' })] }],
    };
    const r = resumir([s, { ...s, id: 's2', estado: 'terminou', grupos: [] }]);
    expect(r.sessoesRodando).toBe(1);
    expect(r.sessoesTotal).toBe(2);
    expect(r.agentesAtivos).toBe(1);
    expect(r.porModelo.map((f) => [f.chave, f.valor])).toEqual([['opus', 1], ['sonnet', 1]]);
    expect(r.porEsforco.map((f) => [f.rotulo, f.valor])).toEqual([['médio', 1], ['muito alto', 1]]);
  });
});

describe('api', () => {
  it('url com todos=1 so quando pedido', () => {
    expect(urlAgentes(false)).toBe('/api/agentes');
    expect(urlAgentes(true)).toBe('/api/agentes?todos=1');
  });
  it('normaliza resposta torta sem quebrar', () => {
    expect(normalizarAgentes(null)).toEqual({ gerado_em: '', avisos: [], sessoes: [] });
    const r = normalizarAgentes({ sessoes: [{ id: 'x', grupos: [{ id: 'g' }] }] });
    expect(r.sessoes[0].grupos[0].agentes).toEqual([]);
  });
});
