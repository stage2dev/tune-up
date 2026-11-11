// Blocos "galeria" (grade de miniaturas) e "midia" (uma imagem ou um video com controles).
// Os arquivos vem da rota GET /api/modulos/<id>/arquivo?c=: so png, jpg, webp, mp4 e webm, sempre dentro da pasta do modulo.
// Uma planilha .csv vira so um link de download (o servidor a manda como anexo, nunca para mostrar).
import { useState, type ReactElement } from 'react';
import { Cartao, EstadoVazio, Selo } from '../../componentes';
import type { Tom } from '../../componentes/Selo';
import { itens, tipoDaMidia, textoOuNada, urlDoArquivo, type BlocoCru } from './interativos';

const TOM_SELO: Record<string, Tom> = { neutro: 'neutro', bom: 'ok', atencao: 'atencao', ruim: 'erro' };

function Aviso({ b, texto }: { b: BlocoCru; texto: string }) {
  return <Cartao titulo={textoOuNada(b.titulo)}><EstadoVazio titulo="Nada para mostrar" texto={texto} /></Cartao>;
}

interface PropsMidia { tipo: 'imagem' | 'video'; url: string; rotulo?: string; classe: string; miniatura?: boolean }

/** Parte pura (testavel sem DOM): a tag com onError ligado, ou o aviso de erro no lugar da imagem quebrada. */
export function conteudoDaMidia({ tipo, url, rotulo, classe, miniatura, falhou, aoFalhar }: PropsMidia & { falhou: boolean; aoFalhar: () => void }): ReactElement {
  if (falhou) {
    return (
      <div role="alert" className={`grid w-full place-items-center rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-4 text-center text-xs text-[var(--color-error)] break-words ${miniatura ? 'aspect-square' : 'min-h-32'}`}>
        Não deu para carregar este arquivo{rotulo ? ` (${rotulo})` : ''}. Ele pode ter sido apagado ou movido.
      </div>
    );
  }
  if (tipo === 'video') {
    return miniatura
      ? <video src={url} preload="metadata" muted playsInline aria-label={rotulo} className={classe} onError={aoFalhar} />
      : <video src={url} controls preload="metadata" playsInline aria-label={rotulo} className={classe} onError={aoFalhar} />;
  }
  return <img src={url} alt={rotulo ?? ''} {...(miniatura ? { loading: 'lazy' as const } : {})} className={classe} onError={aoFalhar} />;
}

export function ArquivoDeMidia(p: PropsMidia) {
  const [falhou, setFalhou] = useState(false);
  return conteudoDaMidia({ ...p, falhou, aoFalhar: () => setFalhou(true) });
}

export function Galeria({ b, moduloId }: { b: BlocoCru; moduloId?: string }) {
  const lista = itens(b.itens).filter((i) => tipoDaMidia(i.arquivo) !== null);
  if (!moduloId) return <Aviso b={b} texto="Esta galeria precisa estar dentro de um módulo." />;
  if (lista.length === 0) return <Aviso b={b} texto={textoOuNada(b.vazio) ?? 'Ainda não há arquivos aqui.'} />;
  return (
    <Cartao titulo={textoOuNada(b.titulo)}>
      <ul className="grid grid-cols-2 md:grid-cols-3 gap-3">
        {lista.map((i, k) => {
          const url = urlDoArquivo(moduloId, String(i.arquivo));
          const rotulo = textoOuNada(i.rotulo) ?? String(i.arquivo).split('/').pop() ?? '';
          const selo = i.selo && typeof i.selo === 'object' ? (i.selo as Record<string, unknown>) : null;
          const seloTexto = selo ? textoOuNada(selo.texto) : undefined;
          return (
            <li key={`${String(i.arquivo)}#${k}`} className="min-w-0 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-secondary)] overflow-hidden">
              <ArquivoDeMidia key={url} tipo={tipoDaMidia(i.arquivo) ?? 'imagem'} url={url} rotulo={rotulo} miniatura
                classe={`w-full aspect-square object-cover${tipoDaMidia(i.arquivo) === 'video' ? ' bg-black' : ''}`} />
              <div className="p-2 grid gap-1 min-w-0">
                <span className="text-xs break-words">{rotulo}</span>
                {seloTexto && <span><Selo estado={seloTexto} rotulo={seloTexto} tom={TOM_SELO[String(selo?.tom)] ?? 'neutro'} /></span>}
              </div>
            </li>
          );
        })}
      </ul>
    </Cartao>
  );
}

/** true se o arquivo e uma planilha .csv (vira link de download). */
export const ehPlanilha = (c: unknown): boolean => typeof c === 'string' && c.toLowerCase().endsWith('.csv');

export function Midia({ b, moduloId }: { b: BlocoCru; moduloId?: string }) {
  const tipo = tipoDaMidia(b.arquivo);
  if (!moduloId) return <Aviso b={b} texto="Esta mídia precisa estar dentro de um módulo." />;
  if (ehPlanilha(b.arquivo)) {
    const nome = String(b.arquivo).split('/').pop() ?? '';
    return (
      <Cartao titulo={textoOuNada(b.titulo)}>
        <a href={urlDoArquivo(moduloId, String(b.arquivo))} download={nome} className="text-sm underline text-[var(--color-accent)] break-words">
          {textoOuNada(b.legenda) ?? `Baixar ${nome}`}
        </a>
      </Cartao>
    );
  }
  if (!tipo) return <Aviso b={b} texto="Este arquivo não é uma imagem (png, jpg, webp) nem um vídeo (mp4, webm)." />;
  const url = urlDoArquivo(moduloId, String(b.arquivo));
  const legenda = textoOuNada(b.legenda);
  return (
    <Cartao titulo={textoOuNada(b.titulo)}>
      <figure className="grid justify-items-center gap-2 m-0">
        <ArquivoDeMidia key={url} tipo={tipo} url={url} rotulo={tipo === 'video' ? textoOuNada(b.alt) ?? legenda : typeof b.alt === 'string' ? b.alt : ''}
          classe={tipo === 'video' ? 'max-w-full max-h-[70vh] rounded-lg bg-black' : 'max-w-full max-h-[70vh] h-auto rounded-lg'} />
        {legenda && <figcaption className="text-xs text-[var(--color-text-secondary)] break-words text-center">{legenda}</figcaption>}
        <a href={url} target="_blank" rel="noopener noreferrer" className="text-sm underline text-[var(--color-accent)]">Abrir o arquivo inteiro</a>
      </figure>
    </Cartao>
  );
}
