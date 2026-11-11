import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router';
import { describe, expect, it } from 'vitest';
import type { Acao, Bloco } from '../../api/tipos';
import { chaves } from '../../api/ganchos';
import { ProvedorAvisos } from '../../componentes';
import { Blocos } from './Blocos';
import { chaveDoBloco, tipoDaMidia, urlDoArquivo } from './interativos';

const acao: Acao = { id: 'x.pedir', grupo: 'g', titulo: 'Pedir peça', descricao: 'Cria uma peça.', risco: 'rascunho', confirmar: true,
  params: [{ nome: 'pedido', rotulo: 'Pedido', tipo: 'texto', obrigatorio: true }] };

function html(blocos: Bloco[], acoes?: Acao[], moduloId: string | null = 'estudio'): string {
  const qc = new QueryClient();
  if (acoes) qc.setQueryData(chaves.acoes, acoes);
  return renderToStaticMarkup(
    createElement(QueryClientProvider, { client: qc }, createElement(MemoryRouter, null, createElement(ProvedorAvisos, null, createElement(Blocos, { blocos, moduloId: moduloId ?? undefined })))),
  );
}

describe('arquivos de midia: logica', () => {
  it('tipo pela extensao, sem diferenciar maiuscula; outra extensao = nada', () => {
    expect(tipoDaMidia('a/b.PNG')).toBe('imagem');
    expect(tipoDaMidia('v.webm')).toBe('video');
    expect(tipoDaMidia('x.svg')).toBeNull();
    expect(tipoDaMidia('x.html')).toBeNull();
    expect(tipoDaMidia(3)).toBeNull();
  });
  it('url escapa o id do modulo e o caminho', () => {
    expect(urlDoArquivo('est/udio', 'a b/c d.png')).toBe('/api/modulos/est%2Fudio/arquivo?c=a%20b%2Fc%20d.png');
  });
});

describe('bloco galeria', () => {
  it('grade com miniatura pela rota, rotulo e selo', () => {
    const h = html([{ tipo: 'galeria', titulo: 'Peças', itens: [
      { arquivo: 'p1/post.png', rotulo: 'Post 1', selo: { texto: 'Aprovada', tom: 'bom' } },
      { arquivo: 'p2/video.mp4', rotulo: 'Vídeo 2' },
    ] }]);
    expect(h).toContain('Peças');
    expect(h).toContain('<img src="/api/modulos/estudio/arquivo?c=p1%2Fpost.png"');
    expect(h).toContain('Post 1');
    expect(h).toContain('Aprovada');
    expect(h).toMatch(/<video src="\/api\/modulos\/estudio\/arquivo\?c=p2%2Fvideo.mp4"/);
  });
  it('item com extensao nao permitida some; sem itens mostra o texto do bloco', () => {
    const h = html([{ tipo: 'galeria', itens: [{ arquivo: 'x.svg', rotulo: 'Perigo' }], vazio: 'Nenhuma peça ainda.' }]);
    expect(h).not.toContain('Perigo');
    expect(h).not.toContain('<img');
    expect(h).toContain('Nenhuma peça ainda.');
  });
  it('fora de um modulo nao monta url', () => {
    const h = html([{ tipo: 'galeria', itens: [{ arquivo: 'a.png' }] }], undefined, null);
    expect(h).not.toContain('/api/modulos');
    expect(h).toContain('precisa estar dentro de um módulo');
  });
});

describe('bloco midia', () => {
  it('video: tag video com controles; imagem: img com alt e legenda', () => {
    const v = html([{ tipo: 'midia', arquivo: 'a/b.mp4', legenda: 'Teaser' }]);
    expect(v).toMatch(/<video[^>]*src="\/api\/modulos\/estudio\/arquivo\?c=a%2Fb.mp4"/);
    expect(v).toMatch(/<video[^>]*controls/);
    expect(v).toContain('Teaser');
    const i = html([{ tipo: 'midia', arquivo: 'a.webp', alt: 'Capa' }]);
    expect(i).toMatch(/<img[^>]*alt="Capa"/);
    expect(i).not.toContain('<video');
  });
  it('arquivo svg ou sem arquivo vira aviso, nunca uma tag', () => {
    for (const arquivo of ['a.svg', 'a.html', '']) {
      const h = html([{ tipo: 'midia', arquivo }]);
      expect(h).not.toMatch(/<(img|video)/);
      expect(h).toContain('não é uma imagem');
    }
  });
});

describe('bloco formulario ligado a acao do catalogo', () => {
  const b: Bloco = { tipo: 'formulario', titulo: 'Novo pedido', catalogo: 'x.pedir', botao: 'Pedir', campos: [
    { id: 'pedido', rotulo: 'Pedido', tipo: 'texto_longo', obrigatorio: true },
    { id: 'formato', rotulo: 'Formato', tipo: 'escolha', opcoes: [{ valor: 'post', rotulo: 'Post' }] },
  ] };
  it('mostra campos e botao; o dialogo de confirmacao so abre no envio', () => {
    const h = html([b], [acao]);
    expect(h).toContain('<textarea');
    expect(h).toContain('Post');
    expect(h).toContain('Pedir');
    expect(h).not.toContain('Quer mesmo');
    expect(h).not.toContain('não existe neste projeto');
  });
  it('enquanto a lista de acoes carrega mostra esqueleto, sem campos', () => {
    const h = html([b]);
    expect(h).toContain('data-skeleton');
    expect(h).not.toContain('<textarea');
  });
  it('acao inexistente: aviso claro, sem formulario', () => {
    const h = html([b], []);
    expect(h).toContain('A ação “x.pedir” não existe neste projeto.');
    expect(h).not.toContain('<form');
  });
  it('chave do bloco com estado muda com a acao do catalogo', () => {
    expect(chaveDoBloco({ ...b }, 0)).toContain('x.pedir');
  });
});
