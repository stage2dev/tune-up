// Caixa de escrever que cresce com o texto. Enter envia; Shift+Enter quebra a linha.
import { useLayoutEffect, useRef, type ReactNode } from 'react';
import { mostrarContador } from './logica';

interface Props {
  valor: string;
  aoMudar: (v: string) => void;
  aoEnviar: () => void;
  max: number;
  rotulo: string;
  placeholder?: string;
  desabilitado?: boolean;
  /** Linhas minimas e altura maxima (px) antes de rolar. */
  linhas?: number;
  alturaMax?: number;
  /** Botao(es) no canto da caixa. */
  children?: ReactNode;
  autoFocus?: boolean;
}

export function CaixaTexto({ valor, aoMudar, aoEnviar, max, rotulo, placeholder, desabilitado, linhas = 3, alturaMax = 320, children, autoFocus }: Props) {
  const ref = useRef<HTMLTextAreaElement>(null);

  useLayoutEffect(() => {
    const t = ref.current;
    if (!t) return;
    t.style.height = 'auto';
    t.style.height = `${Math.min(t.scrollHeight, alturaMax)}px`;
  }, [valor, alturaMax]);

  return (
    <div className="rounded-xl border border-[var(--color-input-border)] bg-[var(--color-input-bg)] focus-within:border-[var(--color-accent)] focus-within:ring-2 focus-within:ring-[var(--color-accent-subtle)] transition-colors">
      <textarea
        ref={ref}
        aria-label={rotulo}
        value={valor}
        maxLength={max}
        rows={linhas}
        placeholder={placeholder}
        disabled={desabilitado}
        autoFocus={autoFocus}
        onChange={(e) => aoMudar(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            aoEnviar();
          }
        }}
        className="block w-full resize-none bg-transparent px-3 pt-3 pb-1 text-sm text-[var(--color-text)] placeholder:text-[var(--color-text-tertiary)] outline-none break-words disabled:opacity-60"
      />
      <div className="flex items-center justify-end gap-2 px-2 pb-2">
        {mostrarContador(valor.length, max) && (
          <span className="mr-auto pl-1 text-xs tabular-nums text-[var(--color-text-tertiary)]" aria-live="polite">
            {valor.length}/{max}
          </span>
        )}
        {children}
      </div>
    </div>
  );
}
