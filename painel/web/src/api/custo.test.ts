import { describe, expect, it } from 'vitest';
import { estadoDoCusto, idsParaCusto, normalizarCusto, urlCusto } from './custo';

const U = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`;

describe('normalizarCusto', () => {
  it('lixo vira mapa vazio, sem quebrar', () => {
    for (const b of [null, undefined, 3, 'x', [], {}, { sessoes: 'x' }, { sessoes: [null, 1, {}, { sessao_id: 5 }] }]) {
      expect(normalizarCusto(b).size).toBe(0);
    }
  });
  it('campo torto vira null, nunca zero', () => {
    const c = normalizarCusto({ sessoes: [{ sessao_id: 'a', encontrada: 'sim', tokens: { total: '9', entrada: NaN }, usd: 'x', contexto_maximo: null, modelos: [null, { modelo: 1 }, { modelo: 'opus', pct: 'a', usd: 2 }] }] }).get('a')!;
    expect(c.encontrada).toBe(false);
    expect(c.tokens).toEqual({ entrada: null, saida: null, cache_escrita: null, cache_leitura: null, total: null });
    expect(c.usd).toBeNull();
    expect(c.modelos).toEqual([{ modelo: 'opus', tokens: null, usd: 2, pct: null }]);
  });
  it('dado bom passa', () => {
    const c = normalizarCusto({ estimativa: true, sessoes: [{ sessao_id: 'a', encontrada: true, parcial: true, tokens: { total: 10 }, usd: 1.5, usd_incompleto: true, subagentes: 2 }] }).get('a')!;
    expect(c).toMatchObject({ encontrada: true, parcial: true, usd: 1.5, usd_incompleto: true, subagentes: 2 });
    expect(c.tokens?.total).toBe(10);
  });
});

describe('ids e url', () => {
  it('so manda UUID completo minusculo, sem repetir', () => {
    const r = idsParaCusto([U(1), 'abc', U(1), 'AAAAAAAA-0000-4000-8000-000000000000', `${U(3)}x`, U(4)]);
    expect(r.enviados).toEqual([U(1), U(4)]);
  });
  it('chave ordenada nao muda com a ordem da tela', () => {
    expect(idsParaCusto([U(2), U(1)]).chave).toEqual(idsParaCusto([U(1), U(2)]).chave);
  });
  it('mais de 60: manda os 60 primeiros da tela; o resto fica de fora', () => {
    const ids = Array.from({ length: 70 }, (_, i) => U(70 - i));
    const r = idsParaCusto(ids);
    expect(r.enviados).toEqual(ids.slice(0, 60));
    expect(r.chave[0] < r.chave[59]).toBe(true);
    expect(urlCusto(r.chave).split('sessao=').length - 1).toBe(60);
  });
  it('url repete sessao=', () => {
    expect(urlCusto([U(1), U(2)])).toBe(`/api/custo?sessao=${U(1)}&sessao=${U(2)}`);
  });
});

describe('estadoDoCusto', () => {
  const base = { mapa: normalizarCusto({ sessoes: [{ sessao_id: U(1), encontrada: true }] }), enviados: new Set([U(1), U(2)]), erro: false, buscando: false };
  it('com dado, mostra o dado mesmo com erro depois', () => {
    expect(estadoDoCusto(U(1), { ...base, erro: true }).tipo).toBe('dados');
  });
  it('ausente: calculando enquanto busca, nao lido depois', () => {
    expect(estadoDoCusto(U(2), { ...base, buscando: true }).tipo).toBe('calculando');
    expect(estadoDoCusto(U(2), base).tipo).toBe('erro');
  });
  it('nao enviada (id estranho ou acima de 60): nao lido, nunca calculando', () => {
    expect(estadoDoCusto('estranho', { ...base, buscando: true }).tipo).toBe('erro');
  });
  it('sem mapa e erro: nao lido', () => {
    expect(estadoDoCusto(U(1), { ...base, mapa: undefined, erro: true }).tipo).toBe('erro');
  });
});
