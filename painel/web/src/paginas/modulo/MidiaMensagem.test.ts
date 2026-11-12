import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it } from 'vitest';
import type { Bloco } from '../../api/tipos';
import { RenderBloco } from './Blocos';
import { carga, CARGA_INICIAL, duracaoCurta, lerMidia, tamanhoCurto, urlDaMidia } from './MidiaMensagem';

const html = (b: Bloco, moduloId: string | null = 'vendas') =>
  renderToStaticMarkup(createElement(QueryClientProvider, { client: new QueryClient() }, createElement(RenderBloco, { bloco: b, moduloId: moduloId ?? undefined })));

const conversa = (midia: unknown, extra: Record<string, unknown> = {}): Bloco =>
  ({ tipo: 'conversa', mensagens: [{ id: 'm1', de: 'contato', texto: '[audio]', tipo: 'audio', quando: '2026-11-11T10:00:00', midia, ...extra }] }) as Bloco;

const srcs = (h: string) => [...h.matchAll(/(?:src|href)="([^"]*)"/g)].map((x) => x[1]);

describe('midia da mensagem: logica', () => {
  it('url so com id do modulo e ref, escapados', () => {
    expect(urlDaMidia('ven/das', 'msg:1')).toBe('/api/modulos/ven%2Fdas/arquivo?ref=msg%3A1');
  });
  it('ref fora da forma ou tipo desconhecido = sem midia', () => {
    for (const ref of ['../x', 'a/b', 'javascript:alert(1)x y', 'data:image/png;base64,AAAA', '.x', 'a..b', '', 'x'.repeat(201)]) {
      expect(lerMidia({ ref, tipo: 'audio' }), ref).toBeNull();
    }
    expect(lerMidia({ ref: 'ok', tipo: 'video' })).toBeNull();
    expect(lerMidia('ok')).toBeNull();
    expect(lerMidia({ ref: 'ok', tipo: 'audio', estado: 'xyz' })?.estado).toBe('pronta');
  });
  it('erro de carga: tenta de novo uma vez, depois falha; dado novo do modulo limpa a falha', () => {
    let c = carga(CARGA_INICIAL, 'erro');
    expect(c.falhou).toBe(false); // primeiro erro (ex.: 503 com as vagas cheias): ainda nao mostra falha
    c = carga(c, 'tentar');
    expect(c.chave).toBe(CARGA_INICIAL.chave + 1); // remonta o elemento: o navegador pede de novo
    c = carga(c, 'erro');
    expect(c.falhou).toBe(true);
    c = carga(c, 'dado-novo');
    expect(c).toEqual({ ...c, falhou: false, restam: 1 });
    expect(carga(c, 'erro').falhou).toBe(false); // de novo com direito a uma tentativa
    expect(carga(CARGA_INICIAL, 'dado-novo')).toBe(CARGA_INICIAL); // sem falha nada muda (o player nao reinicia)
  });
  it('duracao e tamanho curtos', () => {
    expect(duracaoCurta(75)).toBe('1:15');
    expect(duracaoCurta(5)).toBe('0:05');
    expect(tamanhoCurto(500)).toBe('500 B');
    expect(tamanhoCurto(1536)).toBe('1,5 KB');
    expect(tamanhoCurto(3 * 1024 * 1024)).toBe('3 MB');
  });
});

describe('midia da mensagem: tela', () => {
  it('audio: player nativo sem pre-carga, duracao e transcricao escapada', () => {
    const h = html(conversa({ ref: 'msg:1', tipo: 'audio', duracao: 42 }, { transcricao: 'oi <script>alert(1)</script>' }));
    expect(h).toMatch(/<audio[^>]*controls=""[^>]*preload="none"[^>]*src="\/api\/modulos\/vendas\/arquivo\?ref=msg%3A1"/);
    expect(h).toContain('Áudio de 0:42');
    expect(h).toContain('Transcrição: </span>oi &lt;script&gt;alert(1)&lt;/script&gt;');
    expect(h).not.toContain('<script>');
    expect(h).not.toContain('ouça no celular'); // com midia a etiqueta sai
  });
  it('imagem: miniatura preguicosa num botao; a ampliada so monta ao abrir', () => {
    const h = html(conversa({ ref: 'f1', tipo: 'imagem', nome: 'foto.jpg' }, { tipo: 'imagem', texto: 'foto do pedido' }));
    expect(h).toMatch(/<button[^>]*aria-label="Ampliar foto.jpg"[^>]*><img[^>]*src="\/api\/modulos\/vendas\/arquivo\?ref=f1"[^>]*loading="lazy"/);
    expect(h).toContain('max-h-60');
    expect(h).toContain('<dialog');
    expect(h).not.toContain('Fechar');
    expect(h).toContain('foto do pedido');
  });
  it('documento: nome, tamanho e Baixar', () => {
    const h = html(conversa({ ref: 'd1', tipo: 'documento', nome: 'Orçamento <1>.pdf', tamanho: 2048 }, { tipo: 'documento' }));
    expect(h).toContain('Orçamento &lt;1&gt;.pdf');
    expect(h).toContain('2 KB');
    expect(h).toMatch(/<a href="\/api\/modulos\/vendas\/arquivo\?ref=d1" download="Orçamento &lt;1&gt;.pdf"[^>]*>Baixar<\/a>/);
  });
  it('pendente: baixando, sem arquivo', () => {
    const h = html(conversa({ ref: 'p1', tipo: 'audio', estado: 'pendente' }));
    expect(h).toContain('baixando…');
    expect(h).not.toContain('<audio');
    expect(h).not.toContain('arquivo?ref');
  });
  it('falhou com acao: aviso e Tentar de novo; expirada sem acao: so o aviso padrao', () => {
    const h = html(conversa({ ref: 'p1', tipo: 'audio', estado: 'falhou', aviso: 'O WhatsApp não entregou.', acao: { acao: 'baixar', dados: { id: 'p1' } } }));
    expect(h).toContain('O WhatsApp não entregou.');
    expect(h).toContain('Tentar de novo');
    expect(h).not.toContain('<audio');
    const e = html(conversa({ ref: 'p1', tipo: 'imagem', estado: 'expirada' }));
    expect(e).toContain('Este arquivo expirou.');
    expect(e).not.toContain('Tentar de novo');
    expect(e).not.toContain('<img');
  });
  it('transcricao aparece com o audio pendente, expirado, falho ou sem midia valida', () => {
    for (const estado of ['pendente', 'expirada', 'falhou']) {
      const h = html(conversa({ ref: 'a1', tipo: 'audio', estado }, { transcricao: 'quero agendar' }));
      expect(h, estado).toContain('Transcrição: </span>quero agendar');
    }
    expect(html(conversa({ ref: '../x', tipo: 'audio' }, { transcricao: 'quero agendar' }))).toContain('Transcrição: </span>quero agendar');
    expect(html(conversa(undefined, { transcricao: 'quero agendar' }))).toContain('Transcrição: </span>quero agendar');
    const uma = html(conversa({ ref: 'a1', tipo: 'audio' }, { transcricao: 'quero agendar' }));
    expect(uma.split('Transcrição:').length).toBe(2); // uma vez so com o player
  });
  it('sem midia (ou ruim, ou sem id do modulo): fica a etiqueta do tipo', () => {
    expect(html(conversa(undefined))).toContain('Áudio – ouça no celular');
    expect(html(conversa({ ref: '../x', tipo: 'audio' }))).toContain('Áudio – ouça no celular');
    expect(html(conversa({ ref: 'ok', tipo: 'audio' }), null)).toContain('Áudio – ouça no celular');
  });
  it('nenhuma URL javascript: ou data: sai de campo do modulo', () => {
    const ruins = ['javascript:alert(1)', 'data:text/html,x', 'https://evil.example/a.ogg'];
    for (const v of ruins) {
      for (const tipo of ['audio', 'imagem', 'documento']) {
        const h = html(conversa({ ref: 'ok', tipo, nome: v, url: v, src: v }, { transcricao: v }));
        for (const s of srcs(h)) expect(s.startsWith('/api/modulos/vendas/arquivo?ref=')).toBe(true);
        const r = html(conversa({ ref: v, tipo }));
        expect(srcs(r)).toEqual([]);
      }
    }
  });
});
