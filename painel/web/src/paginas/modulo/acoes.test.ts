import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { apiPost, esquecerSessao } from '../../api/cliente';
import type { Acao, Execucao } from '../../api/tipos';
import { acoesDoGrupo, dispararAcao, montarParams, precisaDeDialogo, validarParams } from './acoes';

const base = { descricao: 'd', confirmar: false, params: [] as Acao['params'] };
const foto: Acao = { ...base, id: 'ex.foto', grupo: 'ex', titulo: 'Tirar foto', risco: 'leitura' };
const seo: Acao = {
  ...base, id: 'ex.analise', grupo: 'ex', titulo: 'Analise', risco: 'credito', confirmar: true,
  params: [
    { nome: 'foco', rotulo: 'Foco', tipo: 'escolha', obrigatorio: true, opcoes: ['a', 'b'] },
    { nome: 'pedido', rotulo: 'Pedido', tipo: 'texto', obrigatorio: false, max: 10 },
  ],
};
const dev: Acao = { ...base, id: 'dev.parte', grupo: 'dev', titulo: 'Parte', risco: 'codigo', confirmar: true };

describe('acoes por grupo', () => {
  it('filtra so o grupo pedido', () => {
    expect(acoesDoGrupo([foto, dev, seo], 'ex').map((a) => a.id)).toEqual(['ex.foto', 'ex.analise']);
  });
  it('dialogo so quando confirma ou tem campo', () => {
    expect(precisaDeDialogo(foto)).toBe(false);
    expect(precisaDeDialogo(seo)).toBe(true);
  });
  it('valida obrigatorio, opcao e tamanho', () => {
    expect(validarParams(seo.params, { foco: '', pedido: '' })).toEqual({ foco: 'Escolha uma opção.' });
    expect(validarParams(seo.params, { foco: 'x' }).foco).toBe('Escolha uma das opções.');
    expect(validarParams(seo.params, { foco: 'a', pedido: 'a'.repeat(11) }).pedido).toBe('Máximo de 10 letras.');
    expect(validarParams(seo.params, { foco: 'a', pedido: '' })).toEqual({});
  });
  it('monta params sem campos vazios', () => {
    expect(montarParams(seo.params, { foco: ' a ', pedido: '  ' })).toEqual({ foco: 'a' });
  });
});

describe('disparo (fetch falso)', () => {
  let chamadas: Array<{ url: string; init?: RequestInit }>;
  let fila: Response[];
  const j = (status: number, corpo: unknown) => new Response(JSON.stringify(corpo), { status });
  const sessao = () => j(200, { token: 't', projeto: { nome: 'X' }, versao: '2' });
  const exec = { id: 'abc12345', titulo: 'Analise', estado: 'rodando' } as Execucao;
  const iniciar = (corpo: { acao: string; params: Record<string, string> }) =>
    apiPost<{ execucao: Execucao }>('/api/execucoes', corpo).then((r) => r.execucao);

  beforeEach(() => {
    esquecerSessao();
    chamadas = [];
    fila = [];
    vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
      chamadas.push({ url, init });
      const r = fila.shift();
      if (!r) throw new Error('fila vazia');
      return r;
    });
  });
  afterEach(() => vi.unstubAllGlobals());

  it('201 devolve a execucao e manda acao + params limpos', async () => {
    fila.push(sessao(), j(201, { execucao: exec }));
    const r = await dispararAcao(iniciar, seo, { foco: 'a', pedido: '' });
    expect(r).toEqual({ tipo: 'ok', execucao: exec });
    expect(chamadas[1].url).toBe('/api/execucoes');
    expect(JSON.parse(String(chamadas[1].init?.body))).toEqual({ acao: 'ex.analise', params: { foco: 'a' } });
  });
  it('param faltando nem chama o servidor', async () => {
    const r = await dispararAcao(iniciar, seo, { foco: '' });
    expect(r).toEqual({ tipo: 'erro', mensagem: 'Escolha uma opção.' });
    expect(chamadas).toHaveLength(0);
  });
  it('409 vira ja_rodando com o id para abrir', async () => {
    fila.push(sessao(), j(409, { erro: 'Já está rodando.', execucao_id: 'e9' }));
    expect(await dispararAcao(iniciar, foto, {})).toEqual({ tipo: 'ja_rodando', execucaoId: 'e9', mensagem: 'Já está rodando.' });
  });
  it('400 vira erro com a frase do servidor', async () => {
    fila.push(sessao(), j(400, { erro: 'Ação desconhecida.' }));
    expect(await dispararAcao(iniciar, foto, {})).toEqual({ tipo: 'erro', mensagem: 'Ação desconhecida.' });
  });
});
