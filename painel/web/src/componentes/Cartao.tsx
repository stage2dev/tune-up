// Adaptado de OpenJarvis (Apache-2.0), frontend/src/pages/AgentsPage.tsx (desenho do AgentCard) e index.css (.hud-panel); alterado
import type { ElementType, HTMLAttributes, ReactNode } from 'react';

interface Props extends Omit<HTMLAttributes<HTMLElement>, 'title'> {
  titulo?: ReactNode;
  icone?: ReactNode;
  /** Conteudo no canto direito do cabecalho (ex.: um Selo). */
  acao?: ReactNode;
  como?: ElementType;
  children?: ReactNode;
}

export function Cartao({ titulo, icone, acao, como: Tag = 'section', className = '', children, ...resto }: Props) {
  return (
    <Tag className={`hud-panel p-4 ${className}`} {...resto}>
      {(titulo || acao) && (
        <header className="flex items-center gap-2 mb-3">
          {icone && <span className="text-[var(--color-accent)] shrink-0">{icone}</span>}
          <h3 className="text-sm font-semibold flex-1 min-w-0 truncate">{titulo}</h3>
          {acao}
        </header>
      )}
      {children}
    </Tag>
  );
}
