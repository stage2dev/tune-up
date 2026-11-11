import { describe, expect, it } from 'vitest';
import type { GrupoHabilidade, Habilidade } from '../../api/tipos';
import { agrupar, alternar, etiquetasDe, fatiar, filtrar, idsParaEnviar, incluir, MAX_HABILIDADES, normalizar, podarInexistentes, tirarEnviados } from './habilidades';

const h = (id: string, o: Partial<Habilidade> = {}): Habilidade => ({
  id, nome: `p:${id}`, titulo: id, descricao: '', grupo: 'marketing', origem: 'plug', listada: true, fixa: false, ...o,
});
const grupos: GrupoHabilidade[] = [
  { id: 'marketing', titulo: 'Marketing' },
  { id: 'vendas', titulo: 'Vendas' },
  { id: 'vazio', titulo: 'Vazio' },
];

describe('normalizar e filtrar', () => {
  it('tira acento e maiuscula', () => {
    expect(normalizar('  Ação Rápida ')).toBe('acao rapida');
  });
  it('acha por nome, descricao e origem sem acento', () => {
    const l = [h('a', { descricao: 'Campanha de anúncio' }), h('b', { origem: 'Suas skills' }), h('c')];
    expect(filtrar(l, 'ANUNCIO').map((x) => x.id)).toEqual(['a']);
    expect(filtrar(l, 'suas').map((x) => x.id)).toEqual(['b']);
    expect(filtrar(l, 'plug anuncio').map((x) => x.id)).toEqual(['a']);
    expect(filtrar(l, '').length).toBe(3);
    expect(filtrar(l, 'zzz')).toEqual([]);
  });
});

describe('agrupar', () => {
  it('fixas primeiro, ordem do servidor, sem grupo vazio, grupo desconhecido em Outras', () => {
    const l = [h('v', { grupo: 'vendas' }), h('m'), h('t', { fixa: true, grupo: 'codigo' }), h('x', { grupo: 'novo' })];
    const g = agrupar(grupos, l);
    expect(g.map((x) => x.titulo)).toEqual(['Tune-up (sempre ligado)', 'Marketing', 'Vendas', 'Outras']);
    expect(g[0].fixo).toBe(true);
    expect(g[0].itens.map((x) => x.id)).toEqual(['t']);
  });
  it('a busca esconde grupos sem resultado', () => {
    const g = agrupar(grupos, [h('v', { grupo: 'vendas' }), h('m')], 'v');
    expect(g.map((x) => x.id)).toEqual(['vendas']);
  });
});

describe('alternar', () => {
  it('poe e tira', () => {
    expect(alternar([], 'a')).toEqual({ ids: ['a'], cheio: false });
    expect(alternar(['a', 'b'], 'a')).toEqual({ ids: ['b'], cheio: false });
  });
  it('recusa a setima', () => {
    const seis = ['1', '2', '3', '4', '5', '6'];
    expect(seis.length).toBe(MAX_HABILIDADES);
    expect(alternar(seis, '7')).toEqual({ ids: seis, cheio: true });
    expect(alternar(seis, '6').ids).toEqual(['1', '2', '3', '4', '5']);
  });
});

describe('ids enviados e etiquetas', () => {
  const l = [h('a'), h('f', { fixa: true }), h('b')];
  it('so skills existentes, nao fixas, sem repetir', () => {
    expect(idsParaEnviar(['a', 'f', 'sumiu', 'a', 'b'], l)).toEqual(['a', 'b']);
    expect(idsParaEnviar([], l)).toEqual([]);
  });
  it('etiquetas pulam id que sumiu ou fixo', () => {
    expect(etiquetasDe(['b', 'sumiu', 'f', 'a'], l)).toEqual([{ id: 'b', titulo: 'b' }, { id: 'a', titulo: 'a' }]);
  });
});

describe('incluir (soltar na caixa)', () => {
  it('so poe: ja estando, nao tira e nao avisa', () => {
    expect(incluir(['a', 'b'], 'a')).toEqual({ ids: ['a', 'b'], cheio: false });
    expect(incluir(['a'], 'b')).toEqual({ ids: ['a', 'b'], cheio: false });
  });
  it('com o teto cheio e id novo, avisa sem mexer; id ja presente nao avisa', () => {
    const seis = ['1', '2', '3', '4', '5', '6'];
    expect(incluir(seis, '7')).toEqual({ ids: seis, cheio: true });
    expect(incluir(seis, '3').cheio).toBe(false);
  });
});

describe('tirarEnviados e podarInexistentes', () => {
  it('tira so os enviados; o escolhido durante o envio fica', () => {
    expect(tirarEnviados(['a', 'b', 'c'], ['a', 'b'])).toEqual(['c']);
  });
  it('poda ids que sumiram da lista do servidor', () => {
    expect(podarInexistentes(['a', 'x', 'b'], [h('a'), h('b')])).toEqual(['a', 'b']);
  });
  it('sem mudanca devolve a mesma lista (sem re-render)', () => {
    const l = ['a'];
    expect(podarInexistentes(l, [h('a')])).toBe(l);
    expect(tirarEnviados(l, ['z'])).toBe(l);
  });
});

describe('fatiar', () => {
  it('limita e diz quantos restam', () => {
    const itens = Array.from({ length: 120 }, (_, i) => i);
    expect(fatiar(itens, 50)).toEqual({ visiveis: itens.slice(0, 50), restam: 70 });
    expect(fatiar([1, 2], 50)).toEqual({ visiveis: [1, 2], restam: 0 });
  });
});

describe('agrupar por plugin', () => {
  it('separa pela origem em ordem alfabetica, com as fixas primeiro', () => {
    const l = [h('a', { origem: 'zeta' }), h('b', { origem: 'Alfa' }), h('c', { origem: 'zeta' }), h('t', { fixa: true, origem: 'tune-up' })];
    const g = agrupar(grupos, l, '', 'origem');
    expect(g.map((x) => x.titulo)).toEqual(['Tune-up (sempre ligado)', 'Alfa', 'zeta']);
    expect(g[2].itens.map((x) => x.id)).toEqual(['a', 'c']);
  });
});
