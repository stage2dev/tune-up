import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ErroApi, apiGet, apiPost, esquecerSessao } from './cliente';

type Chamada = { url: string; init?: RequestInit };

function resposta(status: number, corpo: unknown): Response {
  return new Response(corpo === null ? '' : JSON.stringify(corpo), { status });
}

describe('cliente de API', () => {
  let chamadas: Chamada[];
  let fila: Array<Response | Error>;

  beforeEach(() => {
    esquecerSessao();
    chamadas = [];
    fila = [];
    vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
      chamadas.push({ url, init });
      const proximo = fila.shift();
      if (!proximo) throw new Error('sem resposta na fila');
      if (proximo instanceof Error) throw proximo;
      return proximo;
    });
  });
  afterEach(() => vi.unstubAllGlobals());

  const sessao = (token: string) => resposta(200, { token, projeto: { nome: 'X' }, versao: '2' });

  it('GET devolve o JSON e nao manda token', async () => {
    fila.push(resposta(200, { ok: 1 }));
    expect(await apiGet<{ ok: number }>('/api/estado')).toEqual({ ok: 1 });
    expect(chamadas).toHaveLength(1);
    expect(chamadas[0].init).toBeUndefined();
  });

  it('POST pega o token em /api/sessao e manda os dois cabecalhos', async () => {
    fila.push(sessao('abc'), resposta(201, { execucao: { id: 'e1' } }));
    const r = await apiPost<{ execucao: { id: string } }>('/api/execucoes', { acao: 'a', params: {} });
    expect(r.execucao.id).toBe('e1');
    expect(chamadas[0].url).toBe('/api/sessao');
    const h = chamadas[1].init?.headers as Record<string, string>;
    expect(h['X-Painel-Token']).toBe('abc');
    expect(h['Content-Type']).toBe('application/json');
    expect(chamadas[1].init?.body).toBe(JSON.stringify({ acao: 'a', params: {} }));
  });

  it('guarda o token: o segundo POST nao pede sessao de novo', async () => {
    fila.push(sessao('abc'), resposta(200, { ok: true }), resposta(200, { ok: true }));
    await apiPost('/api/x');
    await apiPost('/api/y');
    expect(chamadas.map((c) => c.url)).toEqual(['/api/sessao', '/api/x', '/api/y']);
  });

  it('erro {erro} vira ErroApi com a mensagem e o id do 409', async () => {
    fila.push(sessao('abc'), resposta(409, { erro: 'Já está rodando.', execucao_id: 'e9' }));
    const e = await apiPost('/api/execucoes', {}).catch((x: unknown) => x);
    expect(e).toBeInstanceOf(ErroApi);
    expect((e as ErroApi).message).toBe('Já está rodando.');
    expect((e as ErroApi).status).toBe(409);
    expect((e as ErroApi).execucaoId).toBe('e9');
  });

  it('403 renova o token e tenta uma vez', async () => {
    fila.push(sessao('velho'), resposta(403, { erro: 'token' }), sessao('novo'), resposta(200, { ok: true }));
    expect(await apiPost('/api/x')).toEqual({ ok: true });
    const h = chamadas[3].init?.headers as Record<string, string>;
    expect(h['X-Painel-Token']).toBe('novo');
  });

  it('servidor fora do ar da mensagem simples', async () => {
    fila.push(new TypeError('failed'));
    await expect(apiGet('/api/estado')).rejects.toMatchObject({ status: 0, message: expect.stringContaining('painel') });
  });

  it('resposta que nao e JSON da mensagem com o codigo', async () => {
    fila.push(new Response('<html>', { status: 500 }));
    await expect(apiGet('/api/estado')).rejects.toMatchObject({ status: 500, message: expect.stringContaining('500') });
  });
});
