import { describe, expect, it } from 'vitest';
import { ErroApi } from '../../api/cliente';
import type { Embutido } from '../../api/tipos';
import { botaoDoEmbutido, motivoBloqueio, rotuloEstado, textoEnviando, textoFalha, textoSucesso, tituloFalha } from './logica';

const emb = (p: Partial<Embutido> = {}): Embutido => ({ id: 'estudio', titulo: 'Estúdio', descricao: 'd', ligado: false, disponivel: true, motivo: null, avisos: [], ...p });

describe('botao e estado', () => {
  it('desligado: Ligar primario pede ligar', () => {
    expect(botaoDoEmbutido(emb())).toEqual({ texto: 'Ligar', variante: 'primario', pedir: true });
    expect(rotuloEstado(emb())).toBe('Desligado');
  });
  it('ligado: Desligar secundario pede desligar', () => {
    expect(botaoDoEmbutido(emb({ ligado: true }))).toEqual({ texto: 'Desligar', variante: 'secundario', pedir: false });
    expect(rotuloEstado(emb({ ligado: true }))).toBe('Ligado');
  });
  it('texto enquanto envia', () => {
    expect(textoEnviando(true)).toBe('Ligando…');
    expect(textoEnviando(false)).toBe('Desligando…');
  });
});

describe('indisponivel', () => {
  it('bloqueia ligar e mostra o motivo', () => {
    expect(motivoBloqueio(emb({ disponivel: false, motivo: 'precisa de Docker' }))).toBe('Não dá para ligar neste computador: precisa de Docker');
  });
  it('disponivel ou ja ligado nao bloqueia', () => {
    expect(motivoBloqueio(emb())).toBeNull();
    expect(motivoBloqueio(emb({ ligado: true, disponivel: false, motivo: 'x' }))).toBeNull();
  });
});

describe('avisos', () => {
  it('sucesso e falha, ligar e desligar', () => {
    expect(textoSucesso('Estúdio', true)).toBe('Estúdio ligado — já está no menu');
    expect(textoSucesso('Estúdio', false)).toBe('Estúdio desligado — saiu do menu');
    expect(tituloFalha(true)).toBe('Não deu para ligar');
    expect(tituloFalha(false)).toBe('Não deu para desligar');
  });
  it('traduz erro do servidor, sem servidor e desconhecido', () => {
    expect(textoFalha(new ErroApi('Este módulo não roda no Windows.', 409))).toBe('Este módulo não roda no Windows.');
    expect(textoFalha(new ErroApi('Não consegui falar com o painel. Ele está ligado?', 0))).toBe('Não consegui falar com o painel. Ele está ligado?');
    expect(textoFalha('x')).toBe('Algo deu errado. Tente de novo.');
  });
});
