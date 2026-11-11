import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router';
import { describe, expect, it } from 'vitest';
import type { Bloco } from '../../api/tipos';
import { ErroApi } from '../../api/cliente';
import { ProvedorAvisos } from '../../componentes';
import { Blocos } from './Blocos';
import { avisosDeContraste, lerCores } from './Cores';
import { enviarArquivos, fraseDoFim } from './Envio';
import { chaveDoBloco } from './interativos';
import { comRascunho, conferirArquivo, contraste, corHex, fonteSegura, semRascunho, textoSobre, vistaDaPrevia } from './marca';
import { chipLigado, lerOpcoes } from './Opcoes';

function html(blocos: Bloco[]): string {
  return renderToStaticMarkup(createElement(QueryClientProvider, { client: new QueryClient() },
    createElement(MemoryRouter, null, createElement(ProvedorAvisos, null, createElement(Blocos, { blocos, moduloId: 'estudio' })))));
}
const arquivo = (name: string, type: string, size: number) => ({ name, type, size }) as unknown as File;

describe('cor e contraste', () => {
  it('hex de 3 ou 6 digitos vira #rrggbb minusculo; o resto vira null', () => {
    expect(corHex('#ABC')).toBe('#aabbcc');
    expect(corHex(' #0F6B63 ')).toBe('#0f6b63');
    for (const v of ['red', '#12345', 'url(x)', 3, null]) expect(corHex(v)).toBeNull();
  });
  it('contraste WCAG: preto x branco = 21; #777 x branco fica abaixo de 4,5', () => {
    expect(contraste('#000', '#fff')).toBeCloseTo(21, 5);
    expect(contraste('#777777', '#ffffff')!).toBeLessThan(4.5);
    expect(contraste('#595959', '#ffffff')!).toBeGreaterThanOrEqual(4.5);
    expect(contraste('x', '#fff')).toBeNull();
    expect(textoSobre('#0f6b63')).toBe('#ffffff');
    expect(textoSobre('#fff8ea')).toBe('#000000');
  });
  it('aviso so para par abaixo de 4,5:1, com os rotulos; par com campo inexistente e ignorado', () => {
    const rot = { text: 'Texto', bg: 'Fundo', accent: 'Destaque' };
    const a = avisosDeContraste([{ a: 'text', b: 'bg' }, { a: 'accent', b: 'nada' }], { text: '#888888', bg: '#ffffff', accent: '#000' }, rot);
    expect(a).toHaveLength(1);
    expect(a[0]).toContain('“Texto” e “Fundo”');
    expect(a[0]).toContain('4,5:1');
    expect(avisosDeContraste([{ a: 'text', b: 'bg', aviso: 'Escureça o texto.' }], { text: '#888888', bg: '#ffffff' }, rot)).toEqual(['Escureça o texto.']);
    expect(avisosDeContraste([{ a: 'text', b: 'bg' }], { text: '#111111', bg: '#ffffff' }, rot)).toEqual([]);
  });
  it('fonte so com letras seguras; outra coisa herda', () => {
    expect(fonteSegura("'Fraunces', Georgia, serif")).toBe("'Fraunces', Georgia, serif");
    expect(fonteSegura('x; background:url(http://a)')).toBe('inherit');
    expect(fonteSegura(undefined)).toBe('inherit');
  });
});

describe('rascunho e previa', () => {
  const b = { cores: { fundo: '#fff8ea', texto: '#3a2418', principal: '#5a3220', destaque: '#c8702a' }, fontes: { titulo: 'Georgia', texto: 'Arial' },
    campos: { fundo: 'bg', principal: 'primary', letras: 'letras' } };
  it('sem rascunho: valores do modulo; superficie vazia usa o fundo', () => {
    const v = vistaDaPrevia(b, {});
    expect(v.cores.principal).toBe('#5a3220');
    expect(v.cores.superficie).toBe('#fff8ea');
    expect(v.fontes).toEqual({ titulo: 'Georgia', texto: 'Arial' });
  });
  it('rascunho do campo ligado troca na hora; campo nao ligado nao mexe', () => {
    let r = comRascunho({}, 'primary', { valor: '#112233' });
    r = comRascunho(r, 'letras', { valor: 'classica', fontes: { titulo: 'Fraunces', texto: 'Inter' } });
    r = comRascunho(r, 'accent', { valor: '#000000' }); // destaque nao esta em `campos`
    const v = vistaDaPrevia(b, r);
    expect(v.cores.principal).toBe('#112233');
    expect(v.cores.destaque).toBe('#c8702a');
    expect(v.fontes).toEqual({ titulo: 'Fraunces', texto: 'Inter' });
    expect(vistaDaPrevia(b, semRascunho(r, 'primary')).cores.principal).toBe('#5a3220'); // falhou: volta ao servidor
  });
  it('cor invalida do modulo ou do rascunho cai num padrao, nunca vai crua para o estilo', () => {
    const v = vistaDaPrevia({ cores: { fundo: 'url(javascript:x)' }, campos: { texto: 't' } }, { t: { valor: 'red' } });
    expect(v.cores.fundo).toBe('#ffffff');
    expect(v.cores.texto).toBe('#1a1a1a');
  });
});

describe('bloco cores', () => {
  const bloco: Bloco = { tipo: 'cores', titulo: 'Cores', acao: 'marca.cor', itens: [
    { chave: 'text', rotulo: 'Texto', uso: 'Letras do post', valor: '#888888' }, { chave: 'bg', rotulo: 'Fundo', valor: '#FFF' }, { rotulo: 'sem chave', valor: '#000' } ],
  contraste: [{ a: 'text', b: 'bg' }], botao: { rotulo: 'Pegar as cores da logo', acao: 'marca.cores_da_logo' } };
  it('le so itens com chave e normaliza o valor', () => {
    expect(lerCores((bloco as unknown as { itens: unknown }).itens).map((c) => c.valor)).toEqual(['#888888', '#ffffff']);
  });
  it('input type=color com label ligado, hex visivel, aviso de contraste e botao opcional', () => {
    const h = html([bloco]);
    expect(h.match(/<input[^>]*type="color"/g)).toHaveLength(2);
    const id = /<input id="([^"]+)"[^>]*type="color"[^>]*value="#888888"/.exec(h)?.[1];
    expect(id).toBeTruthy();
    expect(h).toContain(`<label for="${id}"`);
    expect(h).toContain('#ffffff');
    expect(h).toContain('Letras do post');
    expect(h).toContain('ficam difíceis de ler juntas');
    expect(h).toContain('Pegar as cores da logo');
    expect(h).toContain('min-h-11');
  });
  it('sem comando: inputs desligados e aviso', () => {
    const h = html([{ ...bloco, acao: '' } as Bloco]);
    expect(h).toMatch(/type="color"[^>]*disabled/);
    expect(h).toContain('não diz qual comando');
  });
});

describe('bloco opcoes', () => {
  it('cartoes 1 entre N: escolhida com aria-pressed e escrita na fonte da opcao', () => {
    const h = html([{ tipo: 'opcoes', titulo: 'Letras', acao: 'marca.escolher', campo: 'letras', valor: 'b', exemplo: { titulo: 'Pão quentinho' },
      opcoes: [{ valor: 'a', rotulo: 'Clássica', fontes: { titulo: 'Georgia', texto: 'Arial' } }, { valor: 'b', rotulo: 'Moderna', fontes: { titulo: 'Inter' } }] }]);
    expect(h.match(/<button[^>]*aria-pressed="true"/g)).toHaveLength(1);
    expect(h).toContain('Moderna (escolhida)');
    expect(h).toContain('font-family:Georgia');
    expect(h).toContain('Pão quentinho');
  });
  it('chips liga/desliga com aria-pressed do servidor', () => {
    const h = html([{ tipo: 'opcoes', titulo: 'Jeito de falar', acao: 'marca.tom', campo: 'tom', modo: 'varios',
      opcoes: [{ valor: 'proximo', rotulo: 'Próximo', ligado: true }, { valor: 'formal', rotulo: 'Formal' }] }]);
    expect(h).toMatch(/aria-pressed="true"[^>]*>Próximo</);
    expect(h).toMatch(/aria-pressed="false"[^>]*>Formal</);
    expect(h).toContain('rounded-full');
  });
  it('troca local do chip vale ate o servidor mudar', () => {
    const o = lerOpcoes([{ valor: 'x', ligado: false }])[0];
    expect(chipLigado(o, { ligado: true, base: false })).toBe(true);
    expect(chipLigado({ ...o, ligado: true }, { ligado: false, base: false })).toBe(true); // servidor andou: vale ele
    expect(chipLigado(o)).toBe(false);
  });
  it('dois blocos com o mesmo comando e campos diferentes tem chaves diferentes', () => {
    expect(chaveDoBloco({ tipo: 'opcoes', acao: 'm', campo: 'letras' }, 0)).not.toBe(chaveDoBloco({ tipo: 'opcoes', acao: 'm', campo: 'tom' }, 1));
  });
});

describe('bloco previa', () => {
  it('post desenhado com as cores, letras, nome e logo do modulo', () => {
    const h = html([{ tipo: 'previa', nome: 'Forno Miúdo', logo: 'marca/logo.png', cores: { fundo: '#FFF8EA', texto: '#3a2418', principal: '#5a3220', destaque: '#c8702a' },
      fontes: { titulo: 'Georgia' }, textos: { chamada: 'Pão de fermentação natural', numero: '7h' } }]);
    expect(h).toContain('Como vai ficar');
    expect(h).toContain('background:#fff8ea');
    expect(h).toContain('background:#5a3220');
    expect(h).toContain('font-family:Georgia');
    expect(h).toContain('Forno Miúdo');
    expect(h).toContain('7h');
    expect(h).toContain('src="/api/modulos/estudio/arquivo?c=marca%2Flogo.png"');
  });
  it('logo svg nao vira img', () => {
    const h = html([{ tipo: 'previa', nome: 'X', logo: 'logo.svg', cores: { fundo: '#fff', texto: '#000', principal: '#000', destaque: '#000' } }]);
    expect(h).not.toContain('<img');
  });
});

describe('bloco envio', () => {
  it('variante um: previa da imagem atual, botao real e input de arquivo com os tipos aceitos', () => {
    const h = html([{ tipo: 'envio', titulo: 'Logo', destino: 'logo', atual: 'marca/logo.webp' }]);
    expect(h).toContain('src="/api/modulos/estudio/arquivo?c=marca%2Flogo.webp"');
    expect(h).toContain('Trocar a imagem');
    expect(h).toContain('type="file"');
    expect(h).toContain('accept="image/png,image/jpeg,image/webp"');
    expect(h).not.toContain('multiple');
    expect(h).toContain('Arraste a imagem');
  });
  it('grade: fotos com Remover acessivel e input multiplo; sem fotos mostra o vazio', () => {
    const h = html([{ tipo: 'envio', titulo: 'Fotos', destino: 'fotos', variante: 'grade', itens: [{ arquivo: 'fotos/a.jpg', rotulo: 'Fachada' }, { arquivo: 'x.svg' }],
      remover: { acao: 'marca.remover_foto' } }]);
    expect(h).toContain('aria-label="Remover Fachada"');
    expect(h).toContain('multiple');
    expect(h.match(/<img/g)).toHaveLength(1);
    expect(html([{ tipo: 'envio', destino: 'fotos', variante: 'grade', vazio: 'Nenhuma foto ainda.' }])).toContain('Nenhuma foto ainda.');
  });
  it('sem destino: botao desligado e aviso', () => {
    const h = html([{ tipo: 'envio', titulo: 'Logo' } as Bloco]);
    expect(h).toMatch(/<button[^>]*disabled[^>]*>Escolher imagem/);
    expect(h).toContain('não diz para onde');
  });
  it('confere antes de mandar: tipo e tamanho em palavras', () => {
    expect(conferirArquivo({ name: 'a.gif', type: 'image/gif', size: 10 })).toContain('não é uma foto aceita');
    expect(conferirArquivo({ name: 'a.svg', type: 'image/svg+xml', size: 10 })).toContain('PNG, JPG ou WebP');
    expect(conferirArquivo({ name: 'g.png', type: 'image/png', size: 9 * 1024 * 1024 })).toContain('grande demais');
    expect(conferirArquivo({ name: 'g.png', type: 'image/png', size: 3 * 1024 * 1024 }, 2 * 1024 * 1024)).toContain('O limite é 2 MB');
    expect(conferirArquivo({ name: 'ok.webp', type: 'image/webp', size: 1000 })).toBeNull();
  });
  it('manda um de cada vez; o que falha na conferencia nem sai; erro do servidor nao para os outros', async () => {
    const vistos: string[] = [];
    const r = await enviarArquivos([arquivo('a.png', 'image/png', 10), arquivo('b.gif', 'image/gif', 10), arquivo('c.jpg', 'image/jpeg', 10), arquivo('d.webp', 'image/webp', 10)], undefined,
      async (a) => { vistos.push(a.name); if (a.name === 'c.jpg') throw new ErroApi('Tipo de arquivo não aceito aqui (png).', 415); return `fotos/${a.name}`; });
    expect(vistos).toEqual(['a.png', 'c.jpg', 'd.webp']);
    expect(r.feitos).toBe(2);
    expect(r.ultimo).toBe('fotos/d.webp');
    expect(r.erros).toHaveLength(2);
    expect(fraseDoFim(r, true)).toMatch(/^2 fotos enviadas\. .*b\.gif.*c\.jpg.*não aceito/);
    expect(fraseDoFim({ feitos: 1, erros: [], ultimo: 'x' }, false)).toBe('Imagem enviada.');
  });
});
