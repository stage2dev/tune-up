// Gaveta lateral para o celular (lista de conversas, quem esta trabalhando). Esc ou clique fora fecha.
import { useEffect, type ReactNode } from 'react';
import { X } from 'lucide-react';

export function Gaveta({ aberta, lado, titulo, aoFechar, children }: { aberta: boolean; lado: 'esq' | 'dir'; titulo: string; aoFechar: () => void; children: ReactNode }) {
  useEffect(() => {
    if (!aberta) return;
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && aoFechar();
    window.addEventListener('keydown', esc);
    return () => window.removeEventListener('keydown', esc);
  }, [aberta, aoFechar]);
  if (!aberta) return null;
  return (
    <div className="fixed inset-0 z-30">
      <div className="absolute inset-0 bg-black/40" onClick={aoFechar} aria-hidden="true" />
      <aside
        aria-label={titulo}
        className={`absolute inset-y-0 ${lado === 'esq' ? 'left-0 border-r' : 'right-0 border-l'} w-[min(88vw,340px)] bg-[var(--color-surface)] border-[var(--color-border)] flex flex-col`}
      >
        <div className="flex items-center gap-2 px-3 h-12 shrink-0 border-b border-[var(--color-border)]">
          <p className="flex-1 text-sm font-semibold">{titulo}</p>
          <button type="button" onClick={aoFechar} aria-label="Fechar" className="p-1.5 rounded text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-tertiary)]">
            <X size={18} aria-hidden="true" />
          </button>
        </div>
        <div className="flex-1 min-h-0 overflow-y-auto p-3">{children}</div>
      </aside>
    </div>
  );
}
