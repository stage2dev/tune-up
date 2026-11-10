import { Monitor, Moon, Sun } from 'lucide-react';
import { useTema, type Tema } from './tema';

const ROTULO: Record<Tema, string> = { claro: 'Tema claro', escuro: 'Tema escuro', sistema: 'Tema do sistema' };

/** Botao que troca claro -> escuro -> sistema. */
export function BotaoTema() {
  const { tema, alternar } = useTema();
  const Icone = tema === 'claro' ? Sun : tema === 'escuro' ? Moon : Monitor;
  return (
    <button
      type="button"
      onClick={alternar}
      title={`${ROTULO[tema]} (clique para trocar)`}
      aria-label={`${ROTULO[tema]}. Clique para trocar.`}
      className="flex items-center gap-2 w-full px-3 py-2 rounded-lg text-sm text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-tertiary)] hover:text-[var(--color-text)] transition-colors"
    >
      <Icone size={16} aria-hidden="true" />
      <span>{ROTULO[tema]}</span>
    </button>
  );
}
