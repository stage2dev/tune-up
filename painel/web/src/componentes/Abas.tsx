// Abas acessiveis (setas esquerda/direita, Home, End). O conteudo de cada aba e quem usa que renderiza.
import { useId, useRef, type KeyboardEvent, type ReactNode } from 'react';

export interface Aba {
  id: string;
  rotulo: string;
  contador?: number;
}

interface Props {
  abas: Aba[];
  ativa: string;
  aoTrocar: (id: string) => void;
  /** Conteudo da aba ativa. */
  children?: ReactNode;
}

export function Abas({ abas, ativa, aoTrocar, children }: Props) {
  const base = useId();
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});

  const teclado = (e: KeyboardEvent, i: number) => {
    let j = i;
    if (e.key === 'ArrowRight') j = (i + 1) % abas.length;
    else if (e.key === 'ArrowLeft') j = (i - 1 + abas.length) % abas.length;
    else if (e.key === 'Home') j = 0;
    else if (e.key === 'End') j = abas.length - 1;
    else return;
    e.preventDefault();
    aoTrocar(abas[j].id);
    refs.current[abas[j].id]?.focus();
  };

  return (
    <div>
      <div role="tablist" className="flex gap-1 overflow-x-auto border-b border-[var(--color-border)] mb-4">
        {abas.map((a, i) => {
          const sel = a.id === ativa;
          return (
            <button
              key={a.id}
              ref={(el) => {
                refs.current[a.id] = el;
              }}
              role="tab"
              id={`${base}-aba-${a.id}`}
              aria-selected={sel}
              aria-controls={`${base}-painel`}
              tabIndex={sel ? 0 : -1}
              onClick={() => aoTrocar(a.id)}
              onKeyDown={(e) => teclado(e, i)}
              className={`px-3 py-2 text-sm whitespace-nowrap border-b-2 -mb-px transition-colors ${
                sel
                  ? 'border-[var(--color-accent)] text-[var(--color-text)] font-medium'
                  : 'border-transparent text-[var(--color-text-secondary)] hover:text-[var(--color-text)]'
              }`}
            >
              {a.rotulo}
              {a.contador !== undefined && (
                <span className="ml-1.5 text-xs text-[var(--color-text-tertiary)]">{a.contador}</span>
              )}
            </button>
          );
        })}
      </div>
      <div role="tabpanel" id={`${base}-painel`} aria-labelledby={`${base}-aba-${ativa}`}>
        {children}
      </div>
    </div>
  );
}
