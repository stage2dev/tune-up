import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router';
import { describe, expect, it } from 'vitest';
import type { Acao, Bloco } from '../../api/tipos';
import { chaves } from '../../api/ganchos';
import { ProvedorAvisos } from '../../componentes';
import { Blocos, mostrarValor, RenderBloco } from './Blocos';

const acao: Acao = { id: 'x.rodar', grupo: 'g1', titulo: 'Rodar coleta', descricao: 'Coleta os dados.', risco: 'leitura', confirmar: false, params: [] };

function html(blocos: Bloco[], acoes: Acao[] = [acao]): string {
  const qc = new QueryClient();
  qc.setQueryData(chaves.acoes, acoes);
  return renderToStaticMarkup(
    createElement(QueryClientProvider, { client: qc }, createElement(MemoryRouter, null, createElement(ProvedorAvisos, null, createElement(Blocos, { blocos })))),
  );
}

describe('renderizador de blocos', () => {
  it('kpis: mostra rotulo, valor e detalhe; nulo vira "sem dado"', () => {
    const h = html([{ tipo: 'kpis', titulo: 'Resumo', itens: [{ rotulo: 'Vendas', valor: 1234, detalhe: 'no mes', tom: 'bom' }, { rotulo: 'Meta', valor: null }] }]);
    expect(h).toContain('Resumo');
    expect(h).toContain('Vendas');
    expect(h).toContain('1.234');
    expect(h).toContain('no mes');
    expect(h).toContain('sem dado');
  });
  it('tabela: colunas, linhas e alinhamento a direita', () => {
    const h = html([{ tipo: 'tabela', colunas: [{ id: 'a', rotulo: 'Nome' }, { id: 'b', rotulo: 'Total', alinhar: 'dir' }], linhas: [{ a: 'Ana', b: 3 }, { a: 'Bia', b: null }] }]);
    expect(h).toContain('Nome');
    expect(h).toContain('Ana');
    expect(h).toContain('text-right');
    expect(h).toContain('sem dado');
  });
  it('tabela: coluna secundaria some no celular, a principal fica', () => {
    const h = html([{ tipo: 'tabela', colunas: [{ id: 'a', rotulo: 'Campo' }, { id: 'b', rotulo: 'De onde veio', secundaria: true }], linhas: [{ a: 'Cor', b: 'site' }] }]);
    expect(h.match(/hidden sm:table-cell/g)?.length).toBe(2); // th e td da secundaria
    expect(h).toMatch(/<th[^>]*class="(?![^"]*hidden)[^"]*"[^>]*>Campo/);
  });
  it('tabela recolhida: fechada atras do titulo; sem recolhido, aberta', () => {
    const h = html([{ tipo: 'tabela', titulo: 'De onde veio cada dado', recolhido: true, colunas: [{ id: 'a', rotulo: 'Dado' }], linhas: [{ a: 'Cor' }] }]);
    expect(h).toMatch(/<details><summary[^>]*>De onde veio cada dado<\/summary>/);
    expect(h).not.toMatch(/<details[^>]*open/);
    expect(h).toContain('<td');
    expect(html([{ tipo: 'tabela', titulo: 'T', colunas: [{ id: 'a', rotulo: 'A' }], linhas: [{ a: 1 }] }])).not.toContain('<details');
  });
  it('tabela vazia explica com o texto do bloco', () => {
    expect(html([{ tipo: 'tabela', colunas: [{ id: 'a', rotulo: 'A' }], linhas: [], vazio: 'Nada cadastrado ainda.' }])).toContain('Nada cadastrado ainda.');
  });
  it('lista: titulo, detalhe e selo', () => {
    const h = html([{ tipo: 'lista', itens: [{ titulo: 'Item um', detalhe: 'mais info', selo: { texto: 'Urgente', tom: 'ruim' } }] }]);
    expect(h).toContain('Item um');
    expect(h).toContain('mais info');
    expect(h).toContain('Urgente');
  });
  it('lista vazia mostra estado vazio', () => {
    expect(html([{ tipo: 'lista', itens: [] }])).toContain('Nada para mostrar');
  });
  it('serie: com poucos dias explica; com dados desenha o grafico', () => {
    expect(html([{ tipo: 'serie', series: [{ nome: 'A', pontos: [{ x: '2026-11-01', y: 1 }] }] }])).toContain('Ainda poucos dias');
    const h = html([{ tipo: 'serie', titulo: 'Evolucao', series: [{ nome: 'A', pontos: [{ x: '2026-11-01', y: 1 }, { x: '2026-11-02', y: 2 }] }] }]);
    expect(h).toContain('Gráfico de linha: Evolucao');
  });
  it('texto: mantem o conteudo', () => {
    expect(html([{ tipo: 'texto', titulo: 'Nota', texto: 'Leia com calma.' }])).toContain('Leia com calma.');
  });
  it('acoes: mostra so os botoes do grupo pedido', () => {
    const outra: Acao = { ...acao, id: 'x.outra', grupo: 'g2', titulo: 'Outra coisa' };
    const h = html([{ tipo: 'acoes', grupo: 'g1' }], [acao, outra]);
    expect(h).toContain('Rodar coleta');
    expect(h).not.toContain('Outra coisa');
  });
  it('acoes sem acao no grupo explica', () => {
    expect(html([{ tipo: 'acoes', grupo: 'nenhum' }])).toContain('não tem ações cadastradas');
  });
  it('tipo desconhecido vira aviso discreto e nao quebra os vizinhos', () => {
    const h = html([{ tipo: 'foguete' }, { tipo: 'texto', texto: 'continua aqui' }]);
    expect(h).toContain('foguete');
    expect(h).toContain('não é reconhecido');
    expect(h).toContain('continua aqui');
  });
  it('bloco sem tipo e bloco torto nao derrubam', () => {
    expect(renderToStaticMarkup(createElement(RenderBloco, { bloco: { tipo: '' } as Bloco }))).toContain('sem tipo');
    expect(html([{ tipo: 'kpis', itens: 'quebrado' } as unknown as Bloco])).toContain('Nada para mostrar');
  });
  it('aba sem blocos explica', () => {
    expect(html([])).toContain('Esta aba está vazia');
  });
  it('valor nulo nunca vira zero', () => {
    expect(mostrarValor(null)).toBe('sem dado');
    expect(mostrarValor(0)).toBe('0');
  });
});
