import { describe, expect, it } from 'vitest';
import { montarSeries } from './series';

describe('series do grafico', () => {
  const s = [
    { nome: 'A', pontos: [{ x: '2026-11-10', y: 0 }, { x: '2026-11-08', y: 3 }, { x: '2026-11-09', y: null }] },
    { nome: 'B', pontos: [{ x: '2026-11-08', y: null }] },
  ];
  it('ordena por data, nulo continua nulo e zero continua zero', () => {
    const m = montarSeries(s);
    expect(m.linhas.map((l) => l.s0)).toEqual([3, null, 0]);
    expect(m.linhas[0].rotulo).toBe('08/11');
  });
  it('so lista serie com numero e conta datas com dado', () => {
    const m = montarSeries(s);
    expect(m.campos).toEqual([{ campo: 's0', nome: 'A' }]);
    expect(m.comDado).toBe(2);
  });
  it('ignora serie quebrada', () => {
    expect(montarSeries([{ nome: 'x' } as never]).linhas).toEqual([]);
  });
});
