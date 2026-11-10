// Cartoes de nivel do pedido. O escolhido mostra a descricao e "quem vai trabalhar".
import { Loader2, Users } from 'lucide-react';
import type { Acao, StatusModelo } from '../../api/tipos';
import { quemVaiTrabalhar } from './logica';

interface Props {
  niveis: Acao[];
  escolhido: string | null;
  aoEscolher: (id: string) => void;
  status: Record<string, StatusModelo> | undefined;
}

export function SeletorNivel({ niveis, escolhido, aoEscolher, status }: Props) {
  const atual = niveis.find((a) => a.id === escolhido);
  const quem = atual ? quemVaiTrabalhar(atual, status) : null;
  return (
    <div className="grid gap-2">
      <div role="radiogroup" aria-label="Tamanho do pedido" className="flex flex-wrap gap-2">
        {niveis.map((a) => {
          const sel = a.id === escolhido;
          return (
            <button
              key={a.id}
              type="button"
              role="radio"
              aria-checked={sel}
              onClick={() => aoEscolher(a.id)}
              className={`px-3 py-1.5 rounded-full border text-sm transition-colors ${
                sel
                  ? 'bg-[var(--color-accent-subtle)] border-[var(--color-accent)] text-[var(--color-accent)] font-medium'
                  : 'bg-[var(--color-surface)] border-[var(--color-border)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-tertiary)] hover:text-[var(--color-text)]'
              }`}
            >
              {a.titulo}
            </button>
          );
        })}
      </div>
      {atual && quem && (
        <div className="rounded-lg bg-[var(--color-bg-tertiary)] px-3 py-2 text-sm grid gap-1">
          {atual.descricao && <p className="break-words">{atual.descricao}</p>}
          <p className="flex items-start gap-1.5 text-xs text-[var(--color-text-secondary)]">
            {quem.conferindo ? (
              <Loader2 size={13} className="anim-girar shrink-0 mt-px" aria-hidden="true" />
            ) : (
              <Users size={13} className="shrink-0 mt-px" aria-hidden="true" />
            )}
            <span className="break-words">
              <span className="sr-only">Quem vai trabalhar: </span>
              {quem.texto}
            </span>
          </p>
          {quem.aviso && <p className="text-xs text-[var(--color-text-secondary)] break-words">{quem.aviso}</p>}
        </div>
      )}
    </div>
  );
}
