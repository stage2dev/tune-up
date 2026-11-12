import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it } from 'vitest';
import type { Bloco } from '../../api/tipos';
import { Abas } from '../../componentes';
import { RenderBloco } from './Blocos';
import { chavesDosBlocos } from './interativos';

const html = (b: Bloco) =>
  renderToStaticMarkup(createElement(QueryClientProvider, { client: new QueryClient() }, createElement(RenderBloco, { bloco: b, moduloId: 'mod' })));

const conversas = [
  { id: 'c1', titulo: 'Contato Um', detalhe: 'quero saber o preço', quando: '2026-11-11T09:00:00', nao_lidas: 3, selo: { texto: 'IA pausada', tom: 'atencao' } },
  { id: 'c2', titulo: 'Contato <b>Dois</b>', detalhe: 'ok', ativa: true },
];
const caixa: Bloco = {
  tipo: 'caixa', titulo: 'Conversas', conversas, abrir: { acao: 'abrir' },
  conversa: {
    id: 'c2', titulo: 'Contato Dois', enviar: { acao: 'enviar', dados_fixos: { conversa_id: 'c2' } },
    mensagens: [
      { id: 'm1', de: 'contato', texto: '[audio]', tipo: 'audio', quando: '2026-11-10T10:00:00' },
      { id: 'm2', de: 'contato', texto: 'foto do pedido', tipo: 'imagem', quando: '2026-11-11T10:00:00' },
      { id: 'm3', de: 'ia', texto: 'Oi! Como posso ajudar?', quando: '2026-11-11T10:01:00', estado: 'enviado' },
    ],
  },
};

const botoesDasLinhas = (h: string) => h.match(/<button[^>]*type="button"[^>]*>(?:(?!<\/button>).)*<\/button>/g)?.filter((b) => !b.includes('Conversas</button>')) ?? [];

describe('bloco caixa', () => {
  it('linhas sao botoes com titulo, previa, selo e nao lidas; a ativa marcada', () => {
    const h = html(caixa);
    expect(h).not.toContain('não é reconhecido');
    const linhas = botoesDasLinhas(h).filter((b) => b.includes('Contato'));
    expect(linhas).toHaveLength(2);
    expect(linhas[0]).toContain('quero saber o preço');
    expect(linhas[0]).toContain('IA pausada');
    expect(linhas[0]).toMatch(/aria-label="3 não lidas"[^>]*>3</);
    expect(linhas[0]).not.toContain('aria-current');
    expect(linhas[1]).toContain('aria-current="true"');
    expect(linhas[1]).toContain('focus-visible:ring-2');
  });
  it('so texto: titulo com tag aparece escapado', () => {
    const h = html(caixa);
    expect(h).not.toContain('<b>Dois</b>');
    expect(h).toContain('Contato &lt;b&gt;Dois&lt;/b&gt;');
  });
  it('tem busca e a conversa aberta com envio; nao texto vira etiqueta, nunca "[audio]"', () => {
    const h = html(caixa);
    expect(h).toMatch(/<input[^>]*type="search"/);
    expect(h).toContain('<textarea');
    expect(h).toContain('Áudio – ouça no celular');
    expect(h).not.toContain('[audio]');
    expect(h).toContain('Imagem – veja no celular');
    expect(h).toContain('foto do pedido');
    expect(h).toContain('Oi! Como posso ajudar?');
    expect(h).toMatch(/role="separator"[^>]*>.*?(Ontem|\d\d\/\d\d\/\d{4})/);
    expect(h).toContain('10:01');
  });
  it('tela estreita: com conversa aberta a lista some e aparece o voltar', () => {
    const h = html(caixa);
    expect(h).toMatch(/data-painel="lista"[^>]*max-\[769px\]:hidden|max-\[769px\]:hidden[^>]*data-painel="lista"/);
    expect(h).toMatch(/data-painel="conversa" class="min-h-0 "/);
    expect(h).toMatch(/min-\[769px\]:hidden[^>]*>.*Conversas<\/button>/);
    expect(h).toContain('min-[769px]:grid-cols-[320px_minmax(0,1fr)]');
  });
  it('sem conversa aberta: a lista fica e o lado direito explica (some na tela estreita)', () => {
    const h = html({ ...caixa, conversa: undefined, vazio_conversa: 'Escolha alguém.' });
    expect(h).toContain('Escolha alguém.');
    expect(h).toMatch(/data-painel="conversa" class="min-h-0 max-\[769px\]:hidden"/);
    expect(h).not.toMatch(/data-painel="lista"[^>]*max-\[769px\]:hidden/);
    expect(h).not.toContain('<textarea');
  });
  it('lista vazia mostra o texto do modulo; linhas malformadas nao derrubam', () => {
    expect(html({ tipo: 'caixa', conversas: [], abrir: { acao: 'a' }, vazio: 'Nenhum contato ainda.' })).toContain('Nenhum contato ainda.');
    expect(() => html({ tipo: 'caixa', conversas: [null, 3, { id: 1 }], abrir: null, conversa: 'x' } as never)).not.toThrow();
  });
  it('chave estavel: a caixa nao perde o estado quando outros blocos mudam de lugar', () => {
    const [k1] = chavesDosBlocos([caixa]);
    const [, k2] = chavesDosBlocos([{ tipo: 'texto', texto: 'x' }, caixa]);
    expect(k1).toBe(k2);
  });
});

describe('aba com alerta', () => {
  it('mostra o selo so com numero >= 1', () => {
    const h = renderToStaticMarkup(createElement(Abas, { abas: [{ id: 'a', rotulo: 'Conversas', alerta: 4 }, { id: 'b', rotulo: 'Outra', alerta: 0 }], ativa: 'a', aoTrocar: () => {} }));
    expect(h.match(/data-alerta/g)).toHaveLength(1);
    expect(h).toMatch(/aria-label="4 novos"[^>]*>4</);
  });
});
