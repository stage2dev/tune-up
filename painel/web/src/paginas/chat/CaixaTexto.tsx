// Caixa de escrever que cresce com o texto. Enter envia; Shift+Enter quebra a linha.
import { useLayoutEffect, useRef, useState, type DragEvent, type ReactNode } from 'react';
import { TIPO_ARRASTE } from './habilidades';
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
  /** Etiquetas acima do texto. */
  topo?: ReactNode;
  /** Recebe o id da skill arrastada para a caixa. Sem isto, a caixa nao aceita arraste. */
  aoSoltarSkill?: (id: string) => void;
}

export function CaixaTexto({ valor, aoMudar, aoEnviar, max, rotulo, placeholder, desabilitado, linhas = 3, alturaMax = 320, children, autoFocus, topo, aoSoltarSkill }: Props) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const [sobre, setSobre] = useState(false);
  const skillNoArraste = (e: DragEvent) => !!aoSoltarSkill && e.dataTransfer.types.includes(TIPO_ARRASTE);

  useLayoutEffect(() => {
    const t = ref.current;
    if (!t) return;
    t.style.height = 'auto';
    t.style.height = `${Math.min(t.scrollHeight, alturaMax)}px`;
  }, [valor, alturaMax]);

  return (
    <div
      onDragOver={(e) => {
        if (!skillNoArraste(e)) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = 'copy';
        setSobre(true);
      }}
      onDragLeave={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setSobre(false);
      }}
      onDrop={(e) => {
        if (!skillNoArraste(e)) return;
        e.preventDefault();
        setSobre(false);
        const id = e.dataTransfer.getData(TIPO_ARRASTE);
        if (id) aoSoltarSkill?.(id);
      }}
      className={`relative rounded-xl border bg-[var(--color-input-bg)] ${sobre ? 'border-[var(--color-accent)] border-dashed' : 'border-[var(--color-input-border)]'} focus-within:border-[var(--color-accent)] focus-within:ring-2 focus-within:ring-[var(--color-accent-subtle)] transition-colors`}
    >
      {sobre && (
        <div className="absolute inset-0 z-10 flex items-center justify-center rounded-xl bg-[var(--color-accent-subtle)] text-sm font-medium text-[var(--color-accent)] pointer-events-none">
          Solte aqui para usar esta skill
        </div>
      )}
      {topo}
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
