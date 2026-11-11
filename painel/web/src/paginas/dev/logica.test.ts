import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ErroApi, esquecerSessao } from '../../api/cliente';
import type { Execucao } from '../../api/tipos';
import {
  agrupar, casaBusca, estadoEmPalavras, estaNoFim, formatarDuracao, iniciar, juntarPrecisa, lerEstado, ordenarFases,
  moduloDaExecucao, pedidoRodarParte, textoVolta, traduzirErroInicio, ultimoSinal,
} from './logica';
import type { Fase } from './tipos';

const fase = (numero: string, titulo: string, status: ('fechada' | 'pendente')[] | null): Fase => ({
  numero, slug: titulo.toLowerCase().replace(/ /g, '-'), pasta: `${numero}-x`, titulo: `Fase ${numero} - ${titulo}`,
  acompanhada: status !== null,
  partes: (status ?? []).map((s, i) => ({ id: 'ABC'[i], itens_plano: null, status: s, origem: '', parcial: false, pr: null, itens: [], comando_copiar: '' })),
  depois_abertos: null, perguntas_abertas: [], precisa: [], completa: false,
});
const exec = (id: string, estado: Execucao['estado']): Execucao => ({
  id, sessao_id: '', nome: 'n', acao: 'a', area: 'dev', titulo: `T${id}`, params: {}, iniciada_em: '2026-11-10T10:00:00Z', estado, comando_attach: `claude attach ${id}`,
});

describe('fases', () => {
  const fases = [fase('9', 'Velha', ['fechada']), fase('187', 'Experiência do dono', ['fechada', 'pendente']), fase('100', 'Meio', ['fechada']), fase('50', 'Solta', null)];
  it('ordena da mais nova para a mais velha (numerico)', () => {
    expect(ordenarFases(fases).map((f) => f.numero)).toEqual(['187', '100', '50', '9']);
  });
  it('agrupa em abertas, fechadas e sem acompanhamento', () => {
    const g = agrupar(fases, '');
    expect(g.abertas.map((f) => f.numero)).toEqual(['187']);
    expect(g.fechadas.map((f) => f.numero)).toEqual(['100', '9']);
    expect(g.semAcompanhamento.map((f) => f.numero)).toEqual(['50']);
  });
  it('busca por numero, por "fase N" e por nome sem acento', () => {
    expect(agrupar(fases, '187').abertas).toHaveLength(1);
    expect(agrupar(fases, 'fase 100').fechadas).toHaveLength(1);
    expect(casaBusca(fases[1], 'experiencia')).toBe(true);
    expect(casaBusca(fases[1], 'zzz')).toBe(false);
    expect(agrupar(fases, 'zzz').abertas).toHaveLength(0);
  });
  it('texto das voltas de revisao', () => {
    expect(textoVolta({ volta: 1, critico: 0, alto: 1 })).toBe('Volta 1: 1 alto');
    expect(textoVolta({ volta: null, critico: 2, alto: 1 })).toBe('Revisão: 2 críticos e 1 alto');
    expect(textoVolta({ volta: 2, critico: 0, alto: 0 })).toBe('Volta 2: sem achado');
  });
});

describe('estado e inicio', () => {
  it('reconhece estado com erro e estado estranho', () => {
    expect(lerEstado({ erro: 'quebrou', avisos: [] })).toEqual({ erro: 'quebrou' });
    expect(lerEstado(null).erro).toBeTruthy();
    expect(lerEstado({ resumo: {}, fases: [] }).estado).toBeTruthy();
  });
  it('junta pendencias do estado e execucoes que precisam de voce (execucao primeiro)', () => {
    const itens = juntarPrecisa(
      [{ fase: '187', parte: null, tipo: 'pergunta', texto: 'Q1', origem: 'x' }],
      [exec('a', 'rodando'), exec('b', 'precisa_de_voce')],
    );
    expect(itens.map((i) => i.chave.split('-')[0])).toEqual(['exec', 'est']);
    expect(itens[0].para).toBe('/execucoes/b');
    expect(itens[1].titulo).toContain('Fase 187');
  });
});

describe('tempo e rolagem', () => {
  it('formata duracao', () => {
    expect(formatarDuracao(5_000)).toBe('5 s');
    expect(formatarDuracao(192_000)).toBe('3 min 12 s');
    expect(formatarDuracao(3_900_000)).toBe('1 h 05 min');
    expect(formatarDuracao(-5)).toBe('0 s');
  });
  it('ultimo sinal ignora ts vazio', () => {
    expect(ultimoSinal([{ n: 1, ts: '2026-11-10T10:00:00Z', tipo: 'sistema', texto: '' }, { n: 2, ts: '', tipo: 'sistema', texto: '' }])).toBe(Date.parse('2026-11-10T10:00:00Z'));
  });
  it('so acompanha o fim se estava perto dele', () => {
    expect(estaNoFim(1000, 560, 400)).toBe(true);
    expect(estaNoFim(1000, 100, 400)).toBe(false);
  });
});

describe('POST /api/execucoes com fetch falso', () => {
  let chamadas: { url: string; init?: RequestInit }[];
  let fila: Response[];
  beforeEach(() => {
    esquecerSessao();
    chamadas = [];
    fila = [];
    vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
      chamadas.push({ url, init });
      return fila.shift() as Response;
    });
  });
  afterEach(() => vi.unstubAllGlobals());
  const json = (s: number, c: unknown) => new Response(JSON.stringify(c), { status: s });
  const sessao = () => json(200, { token: 'tk', projeto: { nome: 'X' }, versao: '2' });

  it('Rodar Parte manda acao e params certos, com token', async () => {
    fila.push(sessao(), json(201, { execucao: exec('e1', 'rodando') }));
    const e = await iniciar(pedidoRodarParte('187', 'D'));
    expect(e.id).toBe('e1');
    const post = chamadas[1];
    expect(post.url).toBe('/api/execucoes');
    expect(JSON.parse(String(post.init?.body))).toEqual({ acao: 'dev.rodar-parte', params: { fase: '187', parte: 'D' } });
    expect((post.init?.headers as Record<string, string>)['X-Painel-Token']).toBe('tk');
  });
  it('409 vira conflito com o id da execucao que ja roda', async () => {
    fila.push(sessao(), json(409, { erro: 'Essa ação já está rodando.', execucao_id: 'abc12345' }));
    const r = await iniciar(pedidoRodarParte('187', 'D')).catch((x: unknown) => traduzirErroInicio(x));
    expect(r).toEqual({ tipo: 'conflito', texto: 'Essa ação já está rodando.', execucaoId: 'abc12345' });
  });
  it('400 e falha de rede viram erro simples', async () => {
    fila.push(sessao(), json(400, { erro: 'Parte inválida.' }));
    const r = await iniciar(pedidoRodarParte('1', 'Z')).catch((x: unknown) => traduzirErroInicio(x));
    expect(r).toEqual({ tipo: 'erro', texto: 'Parte inválida.' });
    expect(traduzirErroInicio(new ErroApi('x', 0))).toEqual({ tipo: 'erro', texto: 'x' });
    expect(traduzirErroInicio(new Error('qualquer'))).toEqual({ tipo: 'erro', texto: 'Algo deu errado. Tente de novo.' });
  });
});

describe('execucao de modulo', () => {
  const mods = [{ id: 'estudio', titulo: 'Estúdio', alertas: 0 }];
  it('acha o modulo pelo grupo da acao; dev e chat nao sao modulo', () => {
    expect(moduloDaExecucao({ grupo: 'estudio' }, mods)?.titulo).toBe('Estúdio');
    expect(moduloDaExecucao({ area: 'estudio' }, mods)?.id).toBe('estudio');
    expect(moduloDaExecucao({ grupo: 'dev' }, mods)).toBeUndefined();
    expect(moduloDaExecucao({ grupo: 'estudio' }, undefined)).toBeUndefined();
  });
  it('estado em palavras, sem comando de terminal', () => {
    for (const e of ['rodando', 'precisa_de_voce', 'terminou', 'parada', 'sumiu', undefined]) {
      const t = estadoEmPalavras(e, 'Estúdio');
      expect(t).toContain('Estúdio');
      expect(t).not.toMatch(/claude attach|terminal/i);
    }
    expect(estadoEmPalavras('terminou', 'Estúdio')).toBe('Terminou. Veja o resultado em Estúdio.');
  });
});
