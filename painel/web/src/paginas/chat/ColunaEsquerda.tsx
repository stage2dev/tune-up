// Coluna da esquerda do chat: duas abas, "Conversas" e "Skills". A aba escolhida fica lembrada.
import { LateralConversas } from './LateralConversas';
import { LateralSkills } from './LateralSkills';
import type { Acao } from '../../api/tipos';
import type { SkillsDoPedido } from './useSkillsDoPedido';

export type AbaLateral = 'conversas' | 'skills';
const CHAVE_ABA = 'painel.chat.aba';

export function lerAba(): AbaLateral {
  try {
    return window.localStorage.getItem(CHAVE_ABA) === 'skills' ? 'skills' : 'conversas';
  } catch {
    return 'conversas';
  }
}
export function gravarAba(a: AbaLateral): void {
  try {
    window.localStorage.setItem(CHAVE_ABA, a);
  } catch {
    /* sem localStorage: so nao lembra */
  }
}

const ABAS: { id: AbaLateral; titulo: string }[] = [
  { id: 'conversas', titulo: 'Conversas' },
  { id: 'skills', titulo: 'Skills' },
];

interface Props {
  aba: AbaLateral;
  aoTrocar: (a: AbaLateral) => void;
  atual: string | undefined;
  niveis: Acao[];
  skills: SkillsDoPedido;
  aceitaSkills: boolean;
}

export function ColunaEsquerda({ aba, aoTrocar, atual, niveis, skills, aceitaSkills }: Props) {
  return (
    <div className="grid gap-3 content-start min-w-0">
      <div role="group" aria-label="Lista da esquerda" className="grid grid-cols-2 gap-1 rounded-lg bg-[var(--color-bg-tertiary)] p-0.5">
        {ABAS.map((a) => (
          <button
            key={a.id}
            type="button"
            aria-pressed={aba === a.id}
            onClick={() => aoTrocar(a.id)}
            className={`h-8 rounded-md text-sm ${aba === a.id ? 'bg-[var(--color-surface)] font-medium shadow-sm' : 'text-[var(--color-text-secondary)]'}`}
          >
            {a.titulo}
            {a.id === 'skills' && skills.ids.length > 0 && <span className="ml-1 text-xs text-[var(--color-accent)]">({skills.ids.length})</span>}
          </button>
        ))}
      </div>
      {aba === 'skills' ? <LateralSkills skills={skills} aceita={aceitaSkills} /> : <LateralConversas atual={atual} niveis={niveis} />}
    </div>
  );
}
