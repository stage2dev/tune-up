import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ErroApi, apiEnviarArquivo, esquecerSessao, type XhrMinimo } from './cliente';

// XHR falso: guarda o que a tela mandou e responde com o que o teste pediu (nunca aceita "qualquer coisa").
type Resposta = { status: number; corpo?: unknown } | 'rede';
function fabrica(respostas: Resposta[], enviados: { url: string; cab: Record<string, string>; corpo: Blob }[], progresso?: [number, number]) {
  return (): XhrMinimo => {
    const x: XhrMinimo & { url: string; cab: Record<string, string> } = {
      url: '', cab: {}, status: 0, responseText: '', upload: { onprogress: null }, onload: null, onerror: null, onabort: null,
      open(metodo, url) { expect(metodo).toBe('POST'); x.url = url; },
      setRequestHeader(n, v) { x.cab[n] = v; },
      send(corpo) {
        enviados.push({ url: x.url, cab: { ...x.cab }, corpo });
        const r = respostas.shift();
        if (!r) throw new Error('sem resposta na fila');
        queueMicrotask(() => {
          if (r === 'rede') return x.onerror?.();
          if (progresso) x.upload.onprogress?.({ lengthComputable: true, loaded: progresso[0], total: progresso[1] });
          x.status = r.status;
          x.responseText = r.corpo === undefined ? '' : JSON.stringify(r.corpo);
          x.onload?.();
        });
      },
    };
    return x;
  };
}

describe('envio de arquivo cru', () => {
  let sessoes: string[];
  beforeEach(() => {
    esquecerSessao();
    sessoes = [];
    vi.stubGlobal('fetch', async (url: string) => {
      const t = sessoes.shift();
      if (url !== '/api/sessao' || !t) throw new Error('fetch inesperado');
      return new Response(JSON.stringify({ token: t, projeto: { nome: 'X' }, versao: '2' }), { status: 200 });
    });
  });
  afterEach(() => vi.unstubAllGlobals());
  const png = new Blob([new Uint8Array([137, 80, 78, 71])], { type: 'image/png' });

  it('manda os bytes com o token e o tipo, conta o progresso e devolve a resposta', async () => {
    sessoes.push('abc');
    const enviados: { url: string; cab: Record<string, string>; corpo: Blob }[] = [];
    const prog: number[] = [];
    const r = await apiEnviarArquivo<{ c: string }>('/api/modulos/m/envio?destino=logo', png, (p) => prog.push(p),
      fabrica([{ status: 201, corpo: { ok: true, c: 'marca/a.png' } }], enviados, [2, 4]));
    expect(r.c).toBe('marca/a.png');
    expect(enviados).toHaveLength(1);
    expect(enviados[0].url).toBe('/api/modulos/m/envio?destino=logo');
    expect(enviados[0].cab['X-Painel-Token']).toBe('abc');
    expect(enviados[0].cab['Content-Type']).toBe('image/png');
    expect(enviados[0].corpo).toBe(png);
    expect(prog).toEqual([0.5]);
  });

  it('403 renova o token e tenta uma vez so', async () => {
    sessoes.push('velho', 'novo');
    const enviados: { url: string; cab: Record<string, string>; corpo: Blob }[] = [];
    await apiEnviarArquivo('/e', png, undefined, fabrica([{ status: 403, corpo: { erro: 'x' } }, { status: 200, corpo: { ok: true } }], enviados));
    expect(enviados.map((e) => e.cab['X-Painel-Token'])).toEqual(['velho', 'novo']);
    sessoes.push('outro', 'outro2');
    esquecerSessao();
    const e = await apiEnviarArquivo('/e', png, undefined, fabrica([{ status: 403, corpo: { erro: 'Sem permissão.' } }, { status: 403, corpo: { erro: 'Sem permissão.' } }], [])).catch((x: unknown) => x);
    expect(e).toMatchObject({ status: 403 });
  });

  it('erro do servidor vira ErroApi com a frase dele (413, 415)', async () => {
    sessoes.push('abc');
    const e = await apiEnviarArquivo('/e', png, undefined, fabrica([{ status: 413, corpo: { erro: 'Arquivo grande demais (até 8 MB).' } }], [])).catch((x: unknown) => x);
    expect(e).toBeInstanceOf(ErroApi);
    expect((e as ErroApi).message).toBe('Arquivo grande demais (até 8 MB).');
    expect((e as ErroApi).status).toBe(413);
  });

  it('queda de rede da a frase de painel fora do ar; resposta sem JSON da o codigo', async () => {
    sessoes.push('abc');
    await expect(apiEnviarArquivo('/e', png, undefined, fabrica(['rede'], []))).rejects.toMatchObject({ status: 0, message: expect.stringContaining('painel') });
    await expect(apiEnviarArquivo('/e', png, undefined, fabrica([{ status: 500 }], []))).rejects.toMatchObject({ status: 500, message: expect.stringContaining('500') });
  });
});
