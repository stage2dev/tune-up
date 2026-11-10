// Adaptado de OpenJarvis (Apache-2.0), frontend/src/pages/AgentsPage.tsx:86-123 (StatusBadge/StatusDot); alterado
// (cores em color-mix, que funciona com var(); o original concatenava "20" na cor e quebrava)
const COR = {
  neutro: 'var(--color-text-tertiary)',
  destaque: 'var(--color-accent)',
  ok: 'var(--color-success)',
  atencao: 'var(--color-attention)',
  erro: 'var(--color-error)',
} as const;
export type Tom = keyof typeof COR;

// estado -> [texto na tela, tom]
const ESTADOS: Record<string, [string, Tom]> = {
  rodando: ['Rodando', 'destaque'],
  precisa_de_voce: ['Precisa de você', 'atencao'],
  terminou: ['Terminou', 'ok'],
  parada: ['Parada', 'neutro'],
  sumiu: ['Sumiu', 'erro'],
  todo: ['A fazer', 'neutro'],
  doing: ['Fazendo', 'destaque'],
  done: ['Feito', 'ok'],
  dropped: ['Deixado de lado', 'neutro'],
  leitura: ['Só leitura', 'ok'],
  rascunho: ['Rascunho', 'destaque'],
  codigo: ['Mexe no código', 'atencao'],
  credito: ['Gasta crédito', 'erro'],
};

function resolver(estado: string, rotulo?: string, tom?: Tom): [string, Tom] {
  const base = ESTADOS[estado];
  return [rotulo ?? base?.[0] ?? estado.replace(/_/g, ' '), tom ?? base?.[1] ?? 'neutro'];
}

interface Props {
  estado: string;
  rotulo?: string;
  tom?: Tom;
}

export function Selo({ estado, rotulo, tom }: Props) {
  const [texto, t] = resolver(estado, rotulo, tom);
  const cor = COR[t];
  return (
    <span
      className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium whitespace-nowrap"
      style={{ background: `color-mix(in srgb, ${cor} 15%, transparent)`, color: cor }}
    >
      <PontoStatus estado={estado} tom={t} />
      {texto}
    </span>
  );
}

export function PontoStatus({ estado, tom }: { estado: string; tom?: Tom }) {
  const [texto, t] = resolver(estado, undefined, tom);
  return (
    <span
      title={texto}
      aria-hidden="true"
      className={`w-2 h-2 rounded-full inline-block shrink-0 ${estado === 'rodando' || estado === 'doing' ? 'hud-dot-pulse' : ''}`}
      style={{ background: COR[t] }}
    />
  );
}
