import { describe, expect, it } from 'vitest';
import type { ItemLista, ListaAcompanhamento } from '../../api/tipos';
import { areasDe, contarPorArea, filtrarListas, ordenarItens, resumoItens } from './listas';

const lista = (nome: string, area: string, aberta: boolean, atualizado_em: string): ListaAcompanhamento => ({
  nome, area, aberta, atualizado_em, itens: [], estado: {},
});
const L = [
  lista('b-velha', 'beta', true, '2026-10-01T00:00:00Z'),
  lista('outra', 'geral', true, '2026-11-09T00:00:00Z'),
  lista('a-velha', 'alfa', true, '2026-10-05T00:00:00Z'),
  lista('a-nova', 'alfa', true, '2026-11-07T00:00:00Z'),
  lista('b-fechada', 'beta', false, '2026-11-08T00:00:00Z'),
];

describe('listas de trabalho', () => {
  it('areas vem do servidor e das proprias listas', () => {
    expect(areasDe(L, [{ id: 'alfa', titulo: 'Alfa' }]).map((a) => a.id)).toEqual(['alfa', 'beta', 'geral']);
    expect(areasDe(L).map((a) => a.titulo)).toEqual(['Beta', 'Geral', 'Alfa']);
  });
  it('segue a ordem das areas; mais nova antes dentro da area', () => {
    const ordem = areasDe(L, [{ id: 'alfa', titulo: 'Alfa' }, { id: 'beta', titulo: 'Beta' }]);
    expect(filtrarListas(L, 'todas', false, ordem).map((l) => l.nome)).toEqual(['a-nova', 'a-velha', 'b-velha', 'outra']);
  });
  it('fechadas so aparecem quando pedido', () => {
    expect(filtrarListas(L, 'beta', false).map((l) => l.nome)).toEqual(['b-velha']);
    expect(filtrarListas(L, 'beta', true).map((l) => l.nome)).toEqual(['b-fechada', 'b-velha']);
  });
  it('lista sem area cai em geral', () => {
    expect(filtrarListas([lista('x', '', true, '')], 'geral', false)).toHaveLength(1);
  });
  it('conta por area', () => {
    expect(contarPorArea(L, false)).toEqual({ todas: 4, alfa: 2, beta: 1, geral: 1 });
    expect(contarPorArea(L, true).beta).toBe(2);
  });
  it('resume e ordena itens', () => {
    const it = (tarefa: string, status: ItemLista['status']): ItemLista => ({ tarefa, status, notas: '', produtos: [], atualizado_em: '' });
    const itens = [it('a', 'done'), it('b', 'todo'), it('c', 'doing'), it('d', 'dropped')];
    expect(resumoItens(itens)).toEqual({ total: 4, feitos: 1, fazendo: 1, aFazer: 1 });
    expect(ordenarItens(itens).map((i) => i.tarefa)).toEqual(['c', 'b', 'a', 'd']);
  });
});
