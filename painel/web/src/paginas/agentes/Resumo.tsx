// Faixa de resumo do topo: numeros grandes e duas barras empilhadas (modelo e esforco), so CSS.
import type { Fatia, Resumo } from './logica';

function Numero({ valor, rotulo, detalhe }: { valor: number; rotulo: string; detalhe?: string }) {
  return (
    <div className="min-w-0">
      <p className="text-2xl font-semibold tabular-nums leading-tight">{valor}</p>
      <p className="text-xs text-[var(--color-text-secondary)]">{rotulo}</p>
      {detalhe && <p className="text-[11px] text-[var(--color-text-tertiary)]">{detalhe}</p>}
    </div>
  );
}

function Barra({ titulo, fatias }: { titulo: string; fatias: Fatia[] }) {
  const total = fatias.reduce((n, f) => n + f.valor, 0);
  const descricao = fatias.map((f) => `${f.rotulo}: ${f.valor}`).join(', ');
  return (
    <div className="min-w-0 grid gap-1.5">
      <p className="text-xs font-medium text-[var(--color-text-secondary)]">{titulo}</p>
      {total === 0 ? (
        <p className="text-xs text-[var(--color-text-tertiary)]">Nada trabalhando agora.</p>
      ) : (
        <>
          <div className="flex h-2.5 w-full overflow-hidden rounded-full bg-[var(--color-bg-tertiary)]" role="img" aria-label={`${titulo}: ${descricao}`}>
            {fatias.map((f) => (
              <span key={f.chave} style={{ width: `${(f.valor / total) * 100}%`, background: f.cor }} />
            ))}
          </div>
          <ul className="flex flex-wrap gap-x-3 gap-y-1 text-xs" aria-hidden="true">
            {fatias.map((f) => (
              <li key={f.chave} className="inline-flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-sm" style={{ background: f.cor }} />
                <span className="text-[var(--color-text-secondary)]">{f.rotulo}</span>
                <span className="tabular-nums font-medium">{f.valor}</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

export function FaixaResumo({ r }: { r: Resumo }) {
  return (
    <section aria-label="Resumo" className="hud-panel p-4 grid gap-4 md:grid-cols-[auto_auto_1fr_1fr] md:items-start">
      <div className="grid grid-cols-2 gap-4 md:contents">
        <Numero valor={r.sessoesRodando} rotulo={r.sessoesRodando === 1 ? 'sessão trabalhando' : 'sessões trabalhando'} detalhe={`de ${r.sessoesTotal} na lista`} />
        <Numero valor={r.agentesAtivos} rotulo={r.agentesAtivos === 1 ? 'agente ativo' : 'agentes ativos'} />
      </div>
      <Barra titulo="Modelos em uso" fatias={r.porModelo} />
      <Barra titulo="Esforço em uso" fatias={r.porEsforco} />
    </section>
  );
}
