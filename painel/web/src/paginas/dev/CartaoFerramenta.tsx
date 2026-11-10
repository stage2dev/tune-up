// Inspirado no ToolCallCard e no InteractTab do OpenJarvis (Apache-2.0); reescrito para o painel:
// cartao recolhivel por ferramenta, subagente em destaque, erro em vermelho.
import { useState } from 'react';
import { AlertTriangle, Bot, ChevronDown, ChevronRight, Wrench } from 'lucide-react';
import type { EventoExecucao } from '../../api/tipos';
import { horaDoEvento } from './logica';

const primeiraLinha = (t: string): string => (t.split('\n')[0] ?? '').slice(0, 120);

export function CartaoFerramenta({ ev }: { ev: EventoExecucao }) {
  const [aberto, setAberto] = useState(false);
  const sub = ev.tipo === 'subagente';
  const erro = ev.tipo === 'resultado' || ev.erro === true;
  const Icone = erro ? AlertTriangle : sub ? Bot : Wrench;
  const nome = erro ? 'Deu erro' : sub ? `Ajudante${ev.ferramenta ? ` · ${ev.ferramenta}` : ''}` : (ev.ferramenta ?? 'Ferramenta');
  const cor = erro ? 'var(--color-error)' : sub ? 'var(--color-purple)' : 'var(--color-text-secondary)';
  const Seta = aberto ? ChevronDown : ChevronRight;
  return (
    <div
      className="rounded-lg border text-sm overflow-hidden"
      style={{ borderColor: `color-mix(in srgb, ${cor} 35%, transparent)`, background: `color-mix(in srgb, ${cor} 6%, transparent)` }}
    >
      <button type="button" aria-expanded={aberto} onClick={() => setAberto(!aberto)} className="w-full flex items-center gap-2 px-3 py-2 text-left">
        <Seta size={14} aria-hidden="true" className="shrink-0" />
        <Icone size={14} aria-hidden="true" className="shrink-0" style={{ color: cor }} />
        <span className="font-medium shrink-0" style={{ color: cor }}>
          {nome}
        </span>
        {!aberto && <span className="flex-1 min-w-0 truncate text-xs text-[var(--color-text-secondary)]">{primeiraLinha(ev.texto)}</span>}
        {aberto && <span className="flex-1" />}
        <span className="text-xs text-[var(--color-text-tertiary)] shrink-0">{horaDoEvento(ev.ts)}</span>
      </button>
      {aberto && <pre className="px-3 pb-3 text-xs whitespace-pre-wrap break-words font-mono text-[var(--color-text)]">{ev.texto || '(sem texto)'}</pre>}
    </div>
  );
}
