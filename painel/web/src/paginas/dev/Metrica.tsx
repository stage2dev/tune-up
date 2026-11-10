import type { ReactNode } from 'react';

export function Metrica({ rotulo, valor, detalhe, destaque }: { rotulo: string; valor: ReactNode; detalhe?: string; destaque?: boolean }) {
  return (
    <div className="hud-panel p-4 grid grid-cols-1 gap-1 min-w-0" style={destaque ? { borderColor: 'color-mix(in srgb, var(--color-attention) 50%, transparent)' } : undefined}>
      <p className="text-xs text-[var(--color-text-secondary)]">{rotulo}</p>
      <p className="text-2xl font-semibold tabular-nums">{valor}</p>
      {detalhe && <p className="text-xs text-[var(--color-text-tertiary)] truncate">{detalhe}</p>}
    </div>
  );
}
