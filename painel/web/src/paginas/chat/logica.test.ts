import { describe, expect, it } from 'vitest';
import type { Acao, EventoExecucao, Execucao } from '../../api/tipos';
import {
  acoesDoChat,
  comQueSaiu,
  comecoDoPedido,
  conversasDoChat,
  destinoDaExecucao,
  escolherModelo,
  limitePedido,
  montarConversa,
  mostrarContador,
  nivelInicial,
  pedacosDoTexto,
  quemVaiTrabalhar,
  ultimaAcao,
} from './logica';

const acao = (id: string, extra: Partial<Acao> = {}): Acao => ({
  id,
  grupo: 'chat',
  titulo: id,
  descricao: '',
  risco: 'leitura',
  confirmar: false,
  params: [{ nome: 'pedido', rotulo: 'Pedido', tipo: 'texto', obrigatorio: true, max: 4000, linhas: true }],
  ...extra,
});

const ev = (n: number, tipo: EventoExecucao['tipo'], texto = `t${n}`, extra: Partial<EventoExecucao> = {}): EventoExecucao => ({
  n,
  ts: '2026-11-10T10:00:00Z',
  tipo,
  texto,
  ...extra,
});

const exec = (id: string, grupo: string, iniciada_em: string): Execucao => ({
  id,
  sessao_id: '',
  nome: '',
  acao: `${grupo}.x`,
  grupo,
  titulo: id,
  params: { pedido: `pedido ${id}` },
  iniciada_em,
  estado: 'terminou',
  comando_attach: '',
});

describe('escolherModelo', () => {
  it('lista vazia = padrao do CLI', () => {
    expect(escolherModelo([], {})).toEqual({ tipo: 'padrao' });
    expect(escolherModelo(undefined, undefined)).toEqual({ tipo: 'padrao' });
  });
  it('status ainda nao chegou = conferindo (nunca afirma)', () => {
    expect(escolherModelo(['fable', 'opus'], undefined)).toEqual({ tipo: 'conferindo' });
  });
  it('preferido verificando = conferindo', () => {
    expect(escolherModelo(['fable', 'opus'], { fable: 'verificando' })).toEqual({ tipo: 'conferindo' });
  });
  it('preferido sim = ele', () => {
    expect(escolherModelo(['fable', 'opus'], { fable: 'sim' })).toEqual({ tipo: 'ok', modelo: 'fable', semLicenca: [] });
  });
  it('preferido nao = reserva, dizendo qual faltou', () => {
    expect(escolherModelo(['fable', 'opus'], { fable: 'nao' })).toEqual({ tipo: 'ok', modelo: 'opus', semLicenca: ['fable'] });
  });
  it('dois pulados ate o do meio com sim', () => {
    expect(escolherModelo(['fable', 'opus', 'sonnet'], { fable: 'nao', opus: 'sim' })).toEqual({ tipo: 'ok', modelo: 'opus', semLicenca: ['fable'] });
  });
  it('nao_sei = incerto (nao afirma)', () => {
    expect(escolherModelo(['fable', 'opus'], { fable: 'nao_sei' })).toEqual({ tipo: 'incerto', modelo: 'fable', reserva: 'opus' });
  });
  it('um modelo so = reserva, nunca sondado', () => {
    expect(escolherModelo(['sonnet'], {})).toEqual({ tipo: 'ok', modelo: 'sonnet', semLicenca: [] });
  });
});

describe('quemVaiTrabalhar', () => {
  it('texto completo', () => {
    const q = quemVaiTrabalhar({ modelos: ['opus'], esforco: 'medium', equipe: '1 a 2 agentes' }, {});
    expect(q).toEqual({ texto: 'Opus · esforço médio · 1 a 2 agentes', conferindo: false, aviso: null });
  });
  it('conferindo nao cita modelo', () => {
    const q = quemVaiTrabalhar({ modelos: ['fable', 'opus'], esforco: 'xhigh', equipe: '' }, { fable: 'verificando' });
    expect(q.conferindo).toBe(true);
    expect(q.texto).toBe('conferindo sua licença… · esforço muito alto');
    expect(q.texto).not.toMatch(/Fable|Opus/);
  });
  it('caiu na reserva explica em palavras simples', () => {
    const q = quemVaiTrabalhar({ modelos: ['fable', 'opus'], esforco: null, equipe: '' }, { fable: 'nao' });
    expect(q.texto).toBe('Opus');
    expect(q.aviso).toBe('Sua licença não tem o Fable; vai rodar com o Opus.');
  });
  it('servidor antigo sem campos', () => {
    expect(quemVaiTrabalhar({}, undefined).texto).toBe('modelo padrão');
  });
});

describe('comQueSaiu', () => {
  it('junta modelo e esforco; vazio quando nao veio', () => {
    expect(comQueSaiu({ modelo: 'opus', esforco: 'high' })).toBe('Opus · esforço alto');
    expect(comQueSaiu({ modelo: '', esforco: '' })).toBe('');
    expect(comQueSaiu({})).toBe('');
  });
});

describe('niveis', () => {
  const lista = [acao('chat.pergunta'), acao('chat.simples'), { ...acao('dev.x'), grupo: 'dev' }];
  it('filtra o grupo chat sem fixar ids', () => {
    expect(acoesDoChat(lista).map((a) => a.id)).toEqual(['chat.pergunta', 'chat.simples']);
    expect(acoesDoChat(undefined)).toEqual([]);
  });
  it('nivel salvo se existe, senao o primeiro', () => {
    const n = acoesDoChat(lista);
    expect(nivelInicial(n, 'chat.simples')).toBe('chat.simples');
    expect(nivelInicial(n, 'chat.sumido')).toBe('chat.pergunta');
    expect(nivelInicial(n, null)).toBe('chat.pergunta');
    expect(nivelInicial([], null)).toBeNull();
  });
  it('limite vem do max do pedido', () => {
    expect(limitePedido(acao('a'))).toBe(4000);
    expect(limitePedido(acao('a', { params: [] }))).toBe(500);
    expect(mostrarContador(3199, 4000)).toBe(false);
    expect(mostrarContador(3200, 4000)).toBe(true);
  });
});

describe('conversas', () => {
  const lista = [exec('a', 'chat', '2026-11-10T09:00:00Z'), exec('b', 'dev', '2026-11-10T11:00:00Z'), exec('c', 'chat', '2026-11-10T10:00:00Z')];
  it('so chat, mais novas primeiro', () => {
    expect(conversasDoChat(lista).map((e) => e.id)).toEqual(['c', 'a']);
    expect(conversasDoChat(undefined)).toEqual([]);
  });
  it('aceita o nome antigo area', () => {
    const velho = { ...exec('d', 'x', '2026-11-10T09:00:00Z'), grupo: undefined, area: 'chat' };
    expect(conversasDoChat([velho]).map((e) => e.id)).toEqual(['d']);
  });
  it('destino: chat abre a conversa, o resto a tela tecnica', () => {
    expect(destinoDaExecucao(lista[0])).toBe('/conversa/a');
    expect(destinoDaExecucao(lista[1])).toBe('/execucoes/b');
  });
  it('comeco do pedido numa linha', () => {
    expect(comecoDoPedido('muda\n\no  botão')).toBe('muda o botão');
    expect(comecoDoPedido('x'.repeat(100), 10)).toBe(`${'x'.repeat(9)}…`);
    expect(comecoDoPedido(undefined)).toBe('');
  });
});

describe('montarConversa', () => {
  it('esconde o 1o usuario (prompt) e poe o pedido no lugar', () => {
    const itens = montarConversa('muda o botão', [ev(1, 'usuario', 'PROMPT MONTADO'), ev(2, 'assistente', 'feito')]);
    expect(itens.map((i) => i.tipo)).toEqual(['dono', 'claude']);
    expect(itens[0]).toMatchObject({ texto: 'muda o botão' });
    expect(JSON.stringify(itens)).not.toContain('PROMPT MONTADO');
  });
  it('agrupa atividade entre falas e mostra respostas seguintes do dono', () => {
    const itens = montarConversa('p', [
      ev(1, 'usuario'),
      ev(2, 'ferramenta', 'a.ts', { ferramenta: 'Read' }),
      ev(3, 'resultado', 'falhou', { erro: true }),
      ev(4, 'subagente', 'x', { ferramenta: 'Task' }),
      ev(5, 'assistente', 'pergunta?'),
      ev(6, 'usuario', 'sim'),
      ev(7, 'sistema', 'fim'),
      ev(8, 'ferramenta', 'b.ts', { ferramenta: 'Edit' }),
    ]);
    expect(itens.map((i) => i.tipo)).toEqual(['dono', 'atividade', 'claude', 'dono', 'atividade']);
    const a1 = itens[1] as Extract<(typeof itens)[number], { tipo: 'atividade' }>;
    expect(a1.eventos.map((e) => e.n)).toEqual([2, 3, 4]);
    expect(a1.erros).toBe(1);
    expect(itens[3]).toMatchObject({ texto: 'sim' });
    const a2 = itens[4] as typeof a1;
    expect(a2.eventos.map((e) => e.n)).toEqual([7, 8]);
    expect(ultimaAcao(a2.eventos)).toBe('Edit: b.ts');
  });
  it('sem eventos = so o pedido; sem pedido nao inventa balao', () => {
    expect(montarConversa('p', []).map((i) => i.tipo)).toEqual(['dono']);
    expect(montarConversa(undefined, [ev(1, 'usuario')])).toEqual([]);
  });
  it('chaves unicas', () => {
    const itens = montarConversa('p', [ev(1, 'usuario'), ev(2, 'assistente'), ev(3, 'ferramenta'), ev(4, 'assistente'), ev(5, 'usuario')]);
    expect(new Set(itens.map((i) => i.chave)).size).toBe(itens.length);
  });
});

describe('pedacosDoTexto', () => {
  it('separa bloco de codigo e tira a linguagem', () => {
    expect(pedacosDoTexto('antes\n```ts\nconst a = 1;\n```\ndepois')).toEqual([
      { codigo: false, texto: 'antes' },
      { codigo: true, texto: 'const a = 1;' },
      { codigo: false, texto: 'depois' },
    ]);
  });
  it('texto sem bloco fica igual', () => {
    expect(pedacosDoTexto('linha 1\nlinha 2')).toEqual([{ codigo: false, texto: 'linha 1\nlinha 2' }]);
  });
});

describe('montarConversa com skills', () => {
  it('poe as skills no balao do pedido e nas respostas', () => {
    const ev = [
      { n: 1, ts: '', tipo: 'usuario', texto: 'prompt' },
      { n: 2, ts: '', tipo: 'usuario', texto: 'mais uma', habilidades: ['p:x'] },
      { n: 3, ts: '', tipo: 'usuario', texto: 'sem', habilidades: [] },
    ] as EventoExecucao[];
    const itens = montarConversa('oi', ev, ['p:a', 'b']);
    expect(itens[0]).toMatchObject({ tipo: 'dono', habilidades: ['p:a', 'b'] });
    expect(itens[1]).toMatchObject({ tipo: 'dono', habilidades: ['p:x'] });
    expect(itens[2]).toMatchObject({ tipo: 'dono', habilidades: undefined });
  });
});
