// Dialogo de confirmacao acessivel. Usa <dialog>.showModal(): o navegador prende o foco
// dentro dele, fecha com Esc (evento "cancel") e devolve o foco a quem abriu.
import { useEffect, useId, useRef, type ReactNode } from 'react';
import { Botao } from './Botao';

interface Props {
  aberto: boolean;
  titulo: string;
  children?: ReactNode;
  textoConfirmar?: string;
  textoCancelar?: string;
  perigo?: boolean;
  enviando?: boolean;
  aoConfirmar: () => void;
  aoFechar: () => void;
}

export function Dialogo({ aberto, titulo, children, textoConfirmar = 'Confirmar', textoCancelar = 'Cancelar', perigo, enviando, aoConfirmar, aoFechar }: Props) {
  const ref = useRef<HTMLDialogElement>(null);
  const idTitulo = useId();

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (aberto && !d.open) d.showModal();
    if (!aberto && d.open) d.close();
  }, [aberto]);

  return (
    <dialog
      ref={ref}
      aria-labelledby={idTitulo}
      onCancel={(e) => {
        e.preventDefault(); // quem manda e o estado "aberto"
        if (!enviando) aoFechar();
      }}
      onClick={(e) => {
        if (e.target === ref.current && !enviando) aoFechar(); // clique no fundo
      }}
      className="dialogo m-auto w-[min(92vw,440px)] rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text)] shadow-[var(--shadow-lg)] p-0"
    >
      {aberto && (
        <div className="p-5 grid gap-3">
          <h2 id={idTitulo} className="text-base font-semibold">
            {titulo}
          </h2>
          <div className="text-sm text-[var(--color-text-secondary)] grid gap-2">{children}</div>
          <div className="flex justify-end gap-2 pt-2">
            <Botao variante="fantasma" onClick={aoFechar} disabled={enviando} autoFocus>
              {textoCancelar}
            </Botao>
            <Botao variante={perigo ? 'perigo' : 'primario'} onClick={aoConfirmar} enviando={enviando}>
              {textoConfirmar}
            </Botao>
          </div>
        </div>
      )}
    </dialog>
  );
}
