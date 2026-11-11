// Blocos "galeria" (grade de miniaturas) e "midia" (uma imagem ou um video com controles).
// Os arquivos vem da rota GET /api/modulos/<id>/arquivo?c=: so png, jpg, webp, mp4 e webm, sempre dentro da pasta do modulo.
import { Cartao, EstadoVazio, Selo } from '../../componentes';
import type { Tom } from '../../componentes/Selo';
import { itens, tipoDaMidia, textoOuNada, urlDoArquivo, type BlocoCru } from './interativos';

const TOM_SELO: Record<string, Tom> = { neutro: 'neutro', bom: 'ok', atencao: 'atencao', ruim: 'erro' };

function Aviso({ b, texto }: { b: BlocoCru; texto: string }) {
  return <Cartao titulo={textoOuNada(b.titulo)}><EstadoVazio titulo="Nada para mostrar" texto={texto} /></Cartao>;
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
              {tipoDaMidia(i.arquivo) === 'video' ? (
                <video src={url} preload="metadata" muted playsInline aria-label={rotulo} className="w-full aspect-square object-cover bg-black" />
              ) : (
                <img src={url} alt={rotulo} loading="lazy" className="w-full aspect-square object-cover" />
              )}
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

export function Midia({ b, moduloId }: { b: BlocoCru; moduloId?: string }) {
  const tipo = tipoDaMidia(b.arquivo);
  if (!moduloId) return <Aviso b={b} texto="Esta mídia precisa estar dentro de um módulo." />;
  if (!tipo) return <Aviso b={b} texto="Este arquivo não é uma imagem (png, jpg, webp) nem um vídeo (mp4, webm)." />;
  const url = urlDoArquivo(moduloId, String(b.arquivo));
  const legenda = textoOuNada(b.legenda);
  return (
    <Cartao titulo={textoOuNada(b.titulo)}>
      <figure className="grid justify-items-center gap-2 m-0">
        {tipo === 'video' ? (
          <video src={url} controls preload="metadata" playsInline aria-label={textoOuNada(b.alt) ?? legenda} className="max-w-full max-h-[70vh] rounded-lg bg-black" />
        ) : (
          <img src={url} alt={typeof b.alt === 'string' ? b.alt : ''} className="max-w-full max-h-[70vh] h-auto rounded-lg" />
        )}
        {legenda && <figcaption className="text-xs text-[var(--color-text-secondary)] break-words text-center">{legenda}</figcaption>}
      </figure>
    </Cartao>
  );
}
