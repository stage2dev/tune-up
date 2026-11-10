import type { ReactNode } from 'react';

/** Moldura padrao de uma pagina: titulo, subtitulo, acoes e conteudo. */
export function Pagina({ titulo, subtitulo, acoes, children }: { titulo: string; subtitulo?: string; acoes?: ReactNode; children?: ReactNode }) {
  return (
    <div className="anim-entrar mx-auto w-full max-w-5xl p-4 md:p-6">
      <div className="flex flex-wrap items-start gap-3 mb-5">
        <div className="flex-1 min-w-0">
          <h1 className="text-xl font-semibold">{titulo}</h1>
          {subtitulo && <p className="text-sm text-[var(--color-text-secondary)]">{subtitulo}</p>}
        </div>
        {acoes}
      </div>
      {children}
    </div>
  );
}
