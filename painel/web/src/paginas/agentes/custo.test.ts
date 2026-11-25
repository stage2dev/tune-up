import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import type { CustoSessao as Custo, EstadoCusto } from '../../api/custo';
import { CustoSessao } from './CustoSessao';

const base: Custo = {
  sessao_id: 'a', encontrada: true, parcial: false, tokens: { entrada: 1, saida: 1, cache_escrita: 1, cache_leitura: 1, total: 1_200_000 },
  contexto_maximo: 230_000, subagentes: 1, usd: 4.1, usd_incompleto: false,
  modelos: [{ modelo: 'claude-opus-4', tokens: 1, usd: 3.6, pct: 87 }, { modelo: 'haiku', tokens: 1, usd: 0.5, pct: 13 }, { modelo: 'fable', tokens: 1, usd: null, pct: null }],
};
const h = (e: EstadoCusto) => renderToStaticMarkup(createElement(CustoSessao, { estado: e }));
const d = (extra: Partial<Custo>) => h({ tipo: 'dados', custo: { ...base, ...extra } });

describe('CustoSessao', () => {
  it('normal: tokens, contexto, modelos e US$ rotulado como estimativa', () => {
    const html = d({});
    expect(html).toContain('1,2 mi tokens');
    expect(html).toContain('contexto máx. 230 mil');
    expect(html).toContain('Opus');
    expect(html).toContain(' 87%');
    expect(html).toContain('≈ US$ 4,10 (estimativa)');
    expect(html).toContain('fable');
    expect(html).toContain('não é a fatura');
    expect(html).not.toContain('parcial');
  });
  it('carregando e erro: textos proprios, sem zero', () => {
    expect(h({ tipo: 'calculando' })).toContain('calculando custo…');
    expect(h({ tipo: 'erro' })).toContain('custo não lido');
    expect(h({ tipo: 'calculando' })).not.toContain('US$');
  });
  it('sessao nao encontrada', () => {
    expect(d({ encontrada: false, tokens: null, usd: null })).toContain('custo não encontrado');
  });
  it('parcial e incompleto ficam marcados', () => {
    const html = d({ parcial: true, usd_incompleto: true });
    expect(html).toContain('parcial');
    expect(html).toContain('mín. ≈ US$ 4,10');
    expect(html).toContain('incompleto');
  });
  it('sem preco e sem tokens: sem dado, nunca 0', () => {
    const html = d({ usd: null, tokens: null, contexto_maximo: null, modelos: [] });
    expect(html).toContain('sem preço');
    expect(html).toContain('tokens: sem dado');
    expect(html).toContain('contexto máx. sem dado');
    expect(html).not.toContain('US$ 0');
  });
});
