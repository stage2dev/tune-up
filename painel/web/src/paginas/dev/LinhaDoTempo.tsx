// Linha do tempo ao vivo de uma execucao. Rolagem: acompanha o fim; quem subiu para ler nao e puxado de volta.
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { ArrowDown } from 'lucide-react';
import type { EventoExecucao } from '../../api/tipos';
import { CartaoFerramenta } from './CartaoFerramenta';
import { estaNoFim, horaDoEvento } from './logica';

function Evento({ ev }: { ev: EventoExecucao }) {
  switch (ev.tipo) {
    case 'assistente':
      return (
        <div className="grid grid-cols-1 gap-0.5">
          <span className="text-xs text-[var(--color-text-tertiary)]">Claude · {horaDoEvento(ev.ts)}</span>
          <p className="text-sm whitespace-pre-wrap break-words">{ev.texto}</p>
        </div>
      );
    case 'usuario':
      return (
        <details className="rounded-lg bg-[var(--color-accent-subtle)] px-3 py-2 text-sm">
          <summary className="cursor-pointer text-xs font-medium text-[var(--color-accent)]">Pedido enviado · {horaDoEvento(ev.ts)}</summary>
          <p className="mt-2 whitespace-pre-wrap break-words">{ev.texto}</p>
        </details>
      );
    case 'sistema':
      return (
        <p
          className="text-xs text-center break-words"
          style={{ color: ev.erro ? 'var(--color-error)' : 'var(--color-text-secondary)' }}
          role={ev.erro ? 'alert' : undefined}
        >
          {ev.texto}
        </p>
      );
    default:
      return <CartaoFerramenta ev={ev} />;
  }
}

export function LinhaDoTempo({ eventos, vazio }: { eventos: EventoExecucao[]; vazio: string }) {
  const caixa = useRef<HTMLDivElement>(null);
  const noFim = useRef(true);
  const [longe, setLonge] = useState(false);

  const aoRolar = useCallback(() => {
    const c = caixa.current;
    if (!c) return;
    noFim.current = estaNoFim(c.scrollHeight, c.scrollTop, c.clientHeight);
    setLonge(!noFim.current);
  }, []);

  const irAoFim = useCallback(() => {
    const c = caixa.current;
    if (!c) return;
    c.scrollTop = c.scrollHeight;
    noFim.current = true;
    setLonge(false);
  }, []);

  useLayoutEffect(() => {
    if (noFim.current) {
      const c = caixa.current;
      if (c) c.scrollTop = c.scrollHeight;
    }
  }, [eventos.length]);

  useEffect(() => {
    const c = caixa.current;
    if (c) c.scrollTop = c.scrollHeight; // primeira vez: comeca no fim
  }, []);

  return (
    <div className="relative">
      <div
        ref={caixa}
        onScroll={aoRolar}
        role="log"
        aria-live="off"
        aria-label="Linha do tempo da sessão"
        className="grid grid-cols-1 gap-3 content-start overflow-y-auto h-[min(60vh,640px)] rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-3"
      >
        {eventos.length === 0 ? <p className="text-sm text-[var(--color-text-secondary)] text-center py-8">{vazio}</p> : eventos.map((ev) => <Evento key={ev.n} ev={ev} />)}
      </div>
      {longe && (
        <button
          type="button"
          onClick={irAoFim}
          className="absolute bottom-3 right-5 inline-flex items-center gap-1 rounded-full bg-[var(--color-accent)] text-[var(--color-on-accent)] text-xs px-3 py-1.5 shadow-[var(--shadow-lg)]"
        >
          <ArrowDown size={12} aria-hidden="true" />
          Ir para o fim
        </button>
      )}
    </div>
  );
}
