import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { apiPost, esquecerSessao } from '../../api/cliente';
import type { Plugin, RespMudarPlugin } from '../../api/tipos';
import { avisoSobreposto, botaoDoPlugin, detalheSucesso, podeArrastar, criarMovedor, dividirColunas, origemDoValor, pesoEstimado } from './plugins-logica';

const base: Plugin = { id: 'a@m', ligado: true, origem: 'usuario', valores: { usuario: true }, sobreposto: false, fixo: false, skills: 2, agentes: 1, peso: 300 };
const plugin = (o: Partial<Plugin>): Plugin => ({ ...base, ...o });

describe('logica de plugins', () => {
  it('divide em colunas mantendo a ordem', () => {
    const l = [plugin({ id: 'a' }), plugin({ id: 'b', ligado: false }), plugin({ id: 'c' })];
    const { ligados, desligados } = dividirColunas(l);
    expect(ligados.map((p) => p.id)).toEqual(['a', 'c']);
    expect(desligados.map((p) => p.id)).toEqual(['b']);
  });
  it('rotulos de peso e origem', () => {
    expect(pesoEstimado(base)).toBe('2 skills, 1 agente, ~300 caracteres de descrição');
    expect(pesoEstimado(plugin({ skills: 0, agentes: 0, peso: 0 }))).toContain('não sei medir');
    expect(origemDoValor(plugin({ origem: 'local' }))).toContain('locais do projeto');
  });
  it('aviso de sobreposicao so quando o servidor diz', () => {
    expect(avisoSobreposto(base)).toBeNull();
    expect(avisoSobreposto(plugin({ sobreposto: true, origem: 'projeto' }))).toContain('O projeto sobrepõe: mudar aqui não muda');
  });
  it('botao pede o estado oposto', () => {
    expect(botaoDoPlugin(base)).toMatchObject({ texto: 'Desligar', pedir: false });
    expect(botaoDoPlugin(plugin({ ligado: false, valores: { usuario: false } }))).toMatchObject({ texto: 'Ligar', pedir: true });
  });
  it('sobreposto: o botao muda o valor do usuario, nao o que vale', () => {
    // usuario=false, projeto=true: vale true, mas o pedido tem que ser true no settings do usuario
    const a = plugin({ ligado: true, origem: 'projeto', sobreposto: true, valores: { usuario: false, projeto: true } });
    expect(botaoDoPlugin(a)).toMatchObject({ texto: 'Ligar nos seus ajustes', pedir: true });
    const b = plugin({ ligado: false, origem: 'local', sobreposto: true, valores: { usuario: true, local: false } });
    expect(botaoDoPlugin(b)).toMatchObject({ texto: 'Desligar nos seus ajustes', pedir: false });
    expect(podeArrastar(a)).toBe(false); // arrastar = mudar de coluna, e isso o usuario nao consegue aqui
    expect(podeArrastar(base)).toBe(true);
    expect(podeArrastar(plugin({ fixo: true }))).toBe(false);
    const r: RespMudarPlugin = { ok: true, plugins: [{ ...a, valores: { usuario: true, projeto: true } }], aviso: '' };
    expect(detalheSucesso(r, 'a@m')).toContain('continua valendo');
    expect(detalheSucesso({ ...r, plugins: [base] }, 'a@m')).toBeUndefined();
  });
});

describe('movedor de plugins (fetch simulado)', () => {
  let fila: Array<() => Promise<Response>>;
  let urls: string[];
  let lista: Plugin[];
  let eventos: string[];
  const json = (status: number, corpo: unknown) => new Response(JSON.stringify(corpo), { status });
  const ok = (ligado: boolean): RespMudarPlugin => ({ ok: true, plugins: [plugin({ ligado, valores: { usuario: ligado } })], aviso: 'vale na próxima sessão' });
  const novo = () =>
    criarMovedor({
      enviar: (id, enabled) => apiPost<RespMudarPlugin>('/api/plugins', { id, enabled }),
      aoOcupar: (id) => eventos.push(`ocupado:${id}`),
      aoSucesso: (r) => { lista = r.plugins; },
      aoConflito: () => eventos.push('refetch'),
      aoErro: (m) => eventos.push(`erro:${m}`),
    });

  beforeEach(() => {
    esquecerSessao();
    fila = [];
    urls = [];
    eventos = [];
    lista = [plugin({ ligado: true })];
    vi.stubGlobal('fetch', async (url: string) => {
      urls.push(url);
      if (url === '/api/sessao') return json(200, { token: 't', projeto: { nome: 'X' }, versao: '2' });
      const f = fila.shift();
      if (!f) throw new Error('sem resposta na fila');
      return f();
    });
  });
  afterEach(() => vi.unstubAllGlobals());

  it('so move depois da resposta', async () => {
    let liberar!: () => void;
    fila.push(() => new Promise((r) => { liberar = () => r(json(200, ok(false))); }));
    const p = novo()('a@m', false);
    await vi.waitFor(() => expect(liberar).toBeTypeOf('function'));
    expect(lista[0].ligado).toBe(true); // pedido no ar: nada mudou
    liberar();
    expect(await p).toBe('ok');
    expect(lista[0].ligado).toBe(false);
  });
  it('erro: a lista fica e a mensagem do servidor sobe', async () => {
    fila.push(async () => json(403, { erro: 'Sem permissão' }), async () => json(403, { erro: 'Sem permissão' })); // 403 tenta de novo uma vez
    expect(await novo()('a@m', false)).toBe('erro');
    expect(lista[0].ligado).toBe(true);
    expect(eventos).toContain('erro:Sem permissão');
  });
  it('segundo envio durante o primeiro e ignorado', async () => {
    let liberar!: () => void;
    fila.push(() => new Promise((r) => { liberar = () => r(json(200, ok(false))); }));
    const mover = novo();
    const a = mover('a@m', false);
    await vi.waitFor(() => expect(liberar).toBeTypeOf('function'));
    expect(await mover('a@m', false)).toBe('ignorado');
    liberar();
    await a;
    expect(urls.filter((u) => u === '/api/plugins')).toHaveLength(1);
    fila.push(async () => json(200, ok(true)));
    expect(await mover('a@m', true)).toBe('ok'); // liberou depois
  });
  it('409 pede a releitura da lista', async () => {
    fila.push(async () => json(409, { erro: 'mudou' }));
    expect(await novo()('a@m', false)).toBe('conflito');
    expect(eventos).toContain('refetch');
    expect(lista[0].ligado).toBe(true);
  });
  it('200 sem mudar o valor do usuario nao vira sucesso', async () => {
    fila.push(async () => json(200, ok(true))); // pediu false, o servidor devolve usuario ainda true
    expect(await novo()('a@m', false)).toBe('erro');
    expect(eventos.some((e) => e.startsWith('erro:') && e.includes('não mudou'))).toBe(true);
  });
});
