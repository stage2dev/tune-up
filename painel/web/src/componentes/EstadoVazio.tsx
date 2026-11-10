import type { ReactNode } from 'react';
import { Inbox } from 'lucide-react';

/** So mostre depois que o dado chegou (isPending false) e veio sem nada. */
export function EstadoVazio({ titulo, texto, icone, children }: { titulo: string; texto?: string; icone?: ReactNode; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center text-center gap-2 py-10 px-4 text-[var(--color-text-secondary)]">
      <span className="text-[var(--color-text-tertiary)]">{icone ?? <Inbox size={32} aria-hidden="true" />}</span>
      <p className="text-sm font-medium text-[var(--color-text)]">{titulo}</p>
      {texto && <p className="text-xs max-w-sm">{texto}</p>}
      {children}
    </div>
  );
}
