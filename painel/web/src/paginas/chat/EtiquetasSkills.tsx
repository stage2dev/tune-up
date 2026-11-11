// Linha de etiquetas acima do texto: uma por skill escolhida, com x para tirar. Sem skills, nao desenha nada.
import { X } from 'lucide-react';
import { useHabilidades } from '../../api/ganchos';
import { etiquetasDe } from './habilidades';
import type { SkillsDoPedido } from './useSkillsDoPedido';

export function EtiquetasSkills({ skills, desabilitado }: { skills: SkillsDoPedido; desabilitado?: boolean }) {
  const q = useHabilidades();
  const lista = etiquetasDe(skills.ids, q.data?.habilidades ?? []);
  if (lista.length === 0 && !skills.aviso) return null;
  return (
    <div className="flex flex-wrap items-center gap-1.5 px-2 pt-2">
      {lista.map((e) => (
        <span key={e.id} className="inline-flex items-center gap-1 max-w-full rounded-full bg-[var(--color-accent-subtle)] text-[var(--color-accent)] pl-2 pr-1 py-0.5 text-xs">
          <span className="truncate">{e.titulo}</span>
          <button
            type="button"
            aria-label={`Tirar a skill ${e.titulo}`}
            disabled={desabilitado}
            onClick={() => skills.remover(e.id)}
            className="rounded-full p-0.5 hover:bg-[var(--color-bg-tertiary)] disabled:opacity-50"
          >
            <X size={12} aria-hidden="true" />
          </button>
        </span>
      ))}
      {skills.aviso && (
        <span role="status" className="text-xs text-[var(--color-text-secondary)]">
          {skills.aviso}
        </span>
      )}
    </div>
  );
}
