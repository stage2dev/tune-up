import { describe, expect, it } from 'vitest';
import { nomeDoProjeto } from './projeto';

describe('nome do projeto', () => {
  it('usa o nome do servidor', () => expect(nomeDoProjeto({ projeto: { nome: ' Loja ' } })).toBe('Loja'));
  it('cai no padrao', () => {
    expect(nomeDoProjeto(undefined)).toBe('tune-up');
    expect(nomeDoProjeto({})).toBe('tune-up');
    expect(nomeDoProjeto({ projeto: { nome: '' } })).toBe('tune-up');
  });
});
