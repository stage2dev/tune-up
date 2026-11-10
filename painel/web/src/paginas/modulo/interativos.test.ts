import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Bloco } from '../../api/tipos';
import { ErroApi, esquecerSessao } from '../../api/cliente';
import { postarAcao } from '../../api/ganchos';
import { RenderBloco } from './Blocos';
import {
  camposFaltando, dadosDaMensagem, dadosDoFormulario, estaNoFim, imagemSegura, lerCampos, mensagemDoErro, semSegredos, valorDoCampo,
} from './interativos';

const html = (b: Bloco, id = 'mod') =>
  renderToStaticMarkup(createElement(QueryClientProvider, { client: new QueryClient() }, createElement(RenderBloco, { bloco: b, moduloId: id })));

const PNG = 'data:image/png;base64,iVBORw0KGgo=';
const campos = lerCampos([
  { id: 'nome', rotulo: 'Nome', tipo: 'texto', obrigatorio: true, valor: 'Ana' },
  { id: 'chave', rotulo: 'Chave', tipo: 'segredo', valor: 'nao-pode-aparecer' },
  { id: 'cor', rotulo: 'Cor', tipo: 'escolha', opcoes: [{ valor: 'a', rotulo: 'Azul' }] },
  { id: 'x', tipo: 'invalido' },
  { rotulo: 'sem id' },
]);

describe('formulario: logica', () => {
  it('le campos com cuidado: sem id some, tipo estranho vira texto', () => {
    expect(campos.map((c) => c.id)).toEqual(['nome', 'chave', 'cor', 'x']);
    expect(campos[3].tipo).toBe('texto');
  });
  it('segredo nunca vem preenchido; texto usa o valor do servidor ate a pessoa digitar', () => {
    expect(valorDoCampo(campos[1], {})).toBe('');
    expect(valorDoCampo(campos[0], {})).toBe('Ana');
    expect(valorDoCampo(campos[0], { nome: 'Bia' })).toBe('Bia');
    expect(valorDoCampo(campos[0], { nome: '' })).toBe(''); // apagar de proposito vale
  });
  it('obrigatorio vazio (so espacos) e apontado', () => {
    expect(camposFaltando(campos, { nome: '   ' })).toEqual(['nome']);
    expect(camposFaltando(campos, {})).toEqual([]);
  });
  it('dados = dados_fixos + valores; valor do campo ganha do fixo', () => {
    expect(dadosDoFormulario({ a: 1, nome: 'fixo' }, campos, { nome: 'Bia', chave: 'k' })).toEqual({ a: 1, nome: 'Bia', chave: 'k', cor: '', x: '' });
    expect(dadosDoFormulario(null, [], {})).toEqual({});
  });
  it('depois do sucesso so o segredo some', () => {
    expect(semSegredos(campos, { nome: 'Bia', chave: 'k' })).toEqual({ nome: 'Bia' });
  });
});

describe('formulario: tela', () => {
  const b: Bloco = { tipo: 'formulario', titulo: 'Conectar', descricao: 'Preencha.', acao: 'x.salvar', botao: 'Salvar', campos: [
    { id: 'nome', rotulo: 'Nome', tipo: 'texto', obrigatorio: true, valor: 'Ana' },
    { id: 'chave', rotulo: 'Chave', tipo: 'segredo', valor: 'nao-pode-aparecer' },
    { id: 'obs', rotulo: 'Obs', tipo: 'texto_longo' },
    { id: 'cor', rotulo: 'Cor', tipo: 'escolha', opcoes: [{ valor: 'a', rotulo: 'Azul' }] },
  ] };
  it('segredo e senha, sem autocompletar e sem o valor; texto vem preenchido', () => {
    const h = html(b);
    expect(h).toMatch(/<input[^>]*type="password"/);
    expect(h).not.toContain('nao-pode-aparecer');
    expect(h).toMatch(/<input[^>]*type="password"[^>]*autoComplete="off"[^>]*value=""/); // React escreve autoComplete; no DOM vira autocomplete="off"
    expect(h).toContain('value="Ana"');
    expect(h).toContain('<textarea');
    expect(h).toContain('Azul');
    expect(h).toContain('Salvar');
    expect(h).toContain('Conectar');
  });
  it('sem acao: botao desligado e aviso', () => {
    const h = html({ ...b, acao: '' });
    expect(h).toContain('não diz qual ação');
    expect(h).toMatch(/<button[^>]*disabled/);
  });
  it('registrado no renderizador: nao cai no aviso de bloco desconhecido', () => {
    expect(html(b)).not.toContain('não é reconhecido');
  });
});

describe('conversa', () => {
  const b: Bloco = { tipo: 'conversa', titulo: 'Papo', mensagens: [
    { id: '1', de: 'contato', texto: '<script>alert(1)</script> palavralongaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', quando: 'ontem', estado: 'enviado' },
    { id: '2', de: 'ia', texto: 'oi', quando: '2026-11-10T10:00:00', estado: 'incerto', nota: 'sem confirmacao' },
    { id: '3', de: 'eu', texto: 'x', quando: 'q', estado: 'falhou' },
  ], enviar: { acao: 'x.enviar', rotulo: 'Mandar' }, botoes: [{ rotulo: 'Pausar', acao: 'x.pausar', confirmar: 'Pausar mesmo?' }] };
  it('texto e texto puro (escapado), com estados e nota', () => {
    const h = html(b);
    expect(h).not.toContain('<script>');
    expect(h).toContain('&lt;script&gt;');
    expect(h).toContain('Não sei se chegou');
    expect(h).toContain('Falhou');
    expect(h).toContain('sem confirmacao');
    expect(h).toContain('Mandar');
    expect(h).toContain('Pausar');
    expect(h).not.toContain('Pausar mesmo?'); // a confirmacao so aparece depois do clique
  });
  it('vazio mostra o texto do modulo; sem enviar nao ha caixa de texto', () => {
    const h = html({ tipo: 'conversa', mensagens: [], vazio: 'Ninguem falou ainda.' });
    expect(h).toContain('Ninguem falou ainda.');
    expect(h).not.toContain('<textarea');
  });
  it('mensagens malformadas nao derrubam a tela', () => {
    expect(() => html({ tipo: 'conversa', mensagens: [null, 3, { de: 'zzz' }] as never })).not.toThrow();
  });
  it('id_cliente novo a cada envio; dados_fixos entram; texto e id_cliente nao se perdem', () => {
    const a = dadosDaMensagem({ chat: 'c1', texto: 'fixo' }, 'oi');
    const c = dadosDaMensagem({ chat: 'c1' }, 'oi');
    expect(a).toMatchObject({ chat: 'c1', texto: 'oi' });
    expect(typeof a.id_cliente).toBe('string');
    expect(a.id_cliente).not.toBe(c.id_cliente);
    expect(dadosDaMensagem(undefined, 'a', () => 'fixo-1')).toEqual({ texto: 'a', id_cliente: 'fixo-1' });
  });
  it('fio so acompanha se a pessoa ja estava no fim', () => {
    expect(estaNoFim(1000, 600, 400)).toBe(true);
    expect(estaNoFim(1000, 100, 400)).toBe(false);
  });
});

describe('imagem', () => {
  it('png e jpeg aparecem, com alt e legenda', () => {
    const h = html({ tipo: 'imagem', titulo: 'QR', data_uri: PNG, alt: 'Código QR', legenda: 'Aponte a câmera' });
    expect(h).toContain(`src="${PNG}"`);
    expect(h).toContain('alt="Código QR"');
    expect(h).toContain('Aponte a câmera');
    expect(html({ tipo: 'imagem', data_uri: 'data:image/jpeg;base64,/9j/4AAQ', alt: 'a' })).toContain('<img');
  });
  it.each([
    'data:image/svg+xml;base64,PHN2Zz4=', 'javascript:alert(1)', 'https://x.test/a.png', 'data:image/png;base64,AAA" onerror="x', '', 'data:text/html;base64,AAAA',
  ])('recusa %s com o aviso de bloco desconhecido', (uri) => {
    const h = html({ tipo: 'imagem', data_uri: uri, alt: 'a' });
    expect(h).not.toContain('<img');
    expect(h).toContain('não é reconhecido');
    expect(imagemSegura(uri)).toBe(false);
  });
  it('data_uri que nao e texto e recusado', () => {
    expect(html({ tipo: 'imagem', data_uri: 42 as never, alt: 'a' })).not.toContain('<img');
  });
});

describe('POST da acao', () => {
  afterEach(() => { vi.unstubAllGlobals(); esquecerSessao(); });
  const resp = (status: number, corpo: unknown) => new Response(JSON.stringify(corpo), { status });

  it('manda { acao, dados } com token para /api/modulos/<id>/acao', async () => {
    const f = vi.fn(async (url: string) => (url === '/api/sessao' ? resp(200, { token: 'T', projeto: { nome: 'p' }, versao: '1' }) : resp(200, { ok: true, resultado: { n: 1 } })));
    vi.stubGlobal('fetch', f);
    const r = await postarAcao('a b', { acao: 'x.y', dados: { k: 'v' } });
    expect(r).toEqual({ ok: true, resultado: { n: 1 } });
    const [url, init] = f.mock.calls[1] as unknown as [string, RequestInit];
    expect(url).toBe('/api/modulos/a%20b/acao');
    expect(init.method).toBe('POST');
    expect(JSON.parse(String(init.body))).toEqual({ acao: 'x.y', dados: { k: 'v' } });
    expect((init.headers as Record<string, string>)['X-Painel-Token']).toBe('T');
  });
  it('erro do servidor vira ErroApi com a mensagem do servidor', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => (url === '/api/sessao' ? resp(200, { token: 'T', projeto: { nome: 'p' }, versao: '1' }) : resp(409, { erro: 'Já existe.' }))));
    const e = await postarAcao('m', { acao: 'a', dados: {} }).catch((x: unknown) => x);
    expect(e).toBeInstanceOf(ErroApi);
    expect(mensagemDoErro(e)).toBe('Já existe.');
  });
  it('mensagem de 403 sem texto do servidor fica clara', () => {
    expect(mensagemDoErro(new ErroApi('Algo deu errado (código 403).', 403))).toBe('Você não tem permissão para fazer isso.');
    expect(mensagemDoErro(new ErroApi('Sem acesso a isso.', 403))).toBe('Sem acesso a isso.');
    expect(mensagemDoErro('x')).toBe('Algo deu errado.');
  });
});
