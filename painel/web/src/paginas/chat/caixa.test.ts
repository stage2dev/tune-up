import { describe, expect, it } from 'vitest';
import { alternarOpcao, envioDireto, estadoCaixa, textoDasRespostas, type Perguntas } from './caixa';

describe('estadoCaixa', () => {
  it('pode_responder vence sempre: precisa_de_voce com pergunta = Responder sem interromper', () => {
    const c = estadoCaixa({ estado: 'precisa_de_voce', pode_responder: true, pode_interromper: true, temPergunta: true }, true);
    expect(c).toMatchObject({ modo: 'responder', botao: 'Responder', interromper: false, habilitada: true });
    expect(c.dica).toBe('O Claude fez uma pergunta. Responda aqui embaixo.');
  });
  it('pode_responder vence pode_interromper ate rodando', () => {
    expect(estadoCaixa({ estado: 'rodando', pode_responder: true, pode_interromper: true }, false)).toMatchObject({ modo: 'responder', interromper: false });
  });
  it('terminou com pode_responder: Responder, sem aviso de pergunta', () => {
    const c = estadoCaixa({ estado: 'terminou', pode_responder: true }, true);
    expect(c).toMatchObject({ modo: 'responder', botao: 'Responder', dica: null });
  });
  it('terminou com pergunta: aviso de pergunta', () => {
    expect(estadoCaixa({ estado: 'terminou', pode_responder: true, temPergunta: true }, true).dica).toMatch(/fez uma pergunta/);
  });
  it('terminou/parada sem pode_responder: fechada', () => {
    for (const estado of ['terminou', 'parada'] as const) {
      expect(estadoCaixa({ estado, pode_responder: false, pode_interromper: false }, true)).toMatchObject({ modo: 'fechada', habilitada: false, botao: null });
    }
  });
  it('rodando + pode_interromper, caixa vazia: Parar', () => {
    expect(estadoCaixa({ estado: 'rodando', pode_responder: false, pode_interromper: true }, true)).toMatchObject({ modo: 'parar', botao: 'Parar', interromper: false, habilitada: true });
  });
  it('rodando + pode_interromper, com texto: Interromper e enviar', () => {
    const c = estadoCaixa({ estado: 'rodando', pode_responder: false, pode_interromper: true }, false);
    expect(c).toMatchObject({ modo: 'interromper', botao: 'Interromper e enviar', interromper: true });
    expect(c.dica).toMatch(/para o que está fazendo/);
  });
  it('precisa_de_voce sem pode_responder, com pode_interromper: envia interrompendo', () => {
    const c = estadoCaixa({ estado: 'precisa_de_voce', pode_responder: false, pode_interromper: true }, true);
    expect(c).toMatchObject({ modo: 'esperando', botao: 'Enviar', interromper: true, habilitada: true });
    expect(c.dica).toBe('O Claude está esperando uma resposta sua. Escreva aqui embaixo.');
  });
  it('ativa sem pode_interromper: comecando, desabilitada', () => {
    for (const estado of ['rodando', 'precisa_de_voce'] as const) {
      expect(estadoCaixa({ estado, pode_responder: false, pode_interromper: false }, false)).toMatchObject({ modo: 'comecando', habilitada: false, placeholder: 'começando…' });
    }
  });
  it('servidor antigo (sem os campos): ocupado, nunca comecando', () => {
    expect(estadoCaixa({ estado: 'rodando' }, false).modo).toBe('ocupado');
    expect(estadoCaixa({ estado: 'terminou' }, false).modo).toBe('fechada');
  });
  it('sumiu: desabilitada', () => {
    expect(estadoCaixa({ estado: 'sumiu', pode_responder: false }, false)).toMatchObject({ modo: 'sumiu', habilitada: false });
  });
});

const ps = (multipla: boolean, n = 1): Perguntas =>
  Array.from({ length: n }, (_, i) => ({
    pergunta: `Qual cor ${i}?`,
    cabecalho: i === 0 ? 'Cor' : '',
    multipla,
    opcoes: [
      { rotulo: 'Azul', descricao: '' },
      { rotulo: 'Verde', descricao: 'mais calmo' },
    ],
  }));

describe('respostas com opcoes', () => {
  it('envio direto so com uma pergunta de uma escolha', () => {
    expect(envioDireto(ps(false))).toBe(true);
    expect(envioDireto(ps(true))).toBe(false);
    expect(envioDireto(ps(false, 2))).toBe(false);
  });
  it('unica escolha troca; multipla alterna', () => {
    let m = alternarOpcao([], ps(false), 0, 'Azul');
    m = alternarOpcao(m, ps(false), 0, 'Verde');
    expect(m).toEqual([['Verde']]);
    let mm = alternarOpcao([], ps(true), 0, 'Azul');
    mm = alternarOpcao(mm, ps(true), 0, 'Verde');
    expect(mm).toEqual([['Azul', 'Verde']]);
    expect(alternarOpcao(mm, ps(true), 0, 'Azul')).toEqual([['Verde']]);
  });
  it('texto: uma linha por pergunta, cabecalho ou pergunta, rotulos na ordem das opcoes', () => {
    expect(textoDasRespostas(ps(true, 2), [['Verde', 'Azul'], ['Verde']])).toBe('Cor: Azul, Verde\nQual cor 1?: Verde');
  });
  it('pergunta sem marca fica de fora', () => {
    expect(textoDasRespostas(ps(false, 2), [[], ['Azul']])).toBe('Qual cor 1?: Azul');
    expect(textoDasRespostas(ps(false, 2), [])).toBe('');
  });
});

describe('pedido preso no terminal', () => {
  it('avisa que escrever cancela o pedido e manda com interromper', () => {
    const c = estadoCaixa({ estado: 'precisa_de_voce', pode_responder: false, pode_interromper: true, espera_terminal: true }, false);
    expect(c.modo).toBe('esperando');
    expect(c.interromper).toBe(true);
    expect(c.botao).toBe('Cancelar o pedido e enviar');
    expect(c.dica).toMatch(/terminal/);
  });
  it('pergunta escrita continua sendo resposta comum', () => {
    const c = estadoCaixa({ estado: 'precisa_de_voce', pode_responder: true, pode_interromper: true, espera_terminal: false }, false);
    expect(c.modo).toBe('responder');
    expect(c.interromper).toBe(false);
  });
});
