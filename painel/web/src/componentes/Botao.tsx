import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { Loader2 } from 'lucide-react';

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variante?: 'primario' | 'secundario' | 'perigo' | 'fantasma';
  /** true = mostra o giro e bloqueia o clique ("Enviando..."). */
  enviando?: boolean;
  textoEnviando?: string;
  icone?: ReactNode;
}

const VARIANTE = {
  primario: 'bg-[var(--color-accent)] text-[var(--color-on-accent)] hover:bg-[var(--color-accent-hover)] border-transparent',
  secundario: 'bg-[var(--color-surface)] text-[var(--color-text)] border-[var(--color-border)] hover:bg-[var(--color-bg-tertiary)]',
  perigo: 'bg-[var(--color-error)] text-white border-transparent hover:opacity-90',
  fantasma: 'bg-transparent text-[var(--color-text-secondary)] border-transparent hover:bg-[var(--color-bg-tertiary)] hover:text-[var(--color-text)]',
} as const;

export function Botao({ variante = 'primario', enviando = false, textoEnviando = 'Enviando…', icone, disabled, className = '', children, type = 'button', ...resto }: Props) {
  return (
    <button
      type={type}
      disabled={disabled || enviando}
      aria-busy={enviando || undefined}
      className={`inline-flex items-center justify-center gap-2 h-9 px-3.5 rounded-lg border text-sm font-medium transition-colors disabled:opacity-60 ${VARIANTE[variante]} ${className}`}
      {...resto}
    >
      {enviando ? <Loader2 size={14} className="anim-girar" aria-hidden="true" /> : icone}
      {enviando ? textoEnviando : children}
    </button>
  );
}
