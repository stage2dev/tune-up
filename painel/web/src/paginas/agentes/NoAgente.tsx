// Um agente da arvore e, abaixo dele, os filhos (ligados pelas linhas de .ag-ramo).
import { Timer, Wrench } from 'lucide-react';
import { duracaoAgente, formatarDuracao, type No } from './logica';
import { ChipModelo, MedidorEsforco, PontoAgente } from './pecas';

export function NoAgente({ no, agora }: { no: No; agora: number }) {
  const a = no.agente;
  const rodando = a.estado === 'rodando';
  const dur = formatarDuracao(duracaoAgente(a, agora));
  return (
    <li className="ag-ramo pt-2" data-agente={a.id}>
      <div
        className="rounded-lg border p-2.5 grid gap-1.5"
        style={{
          borderColor: rodando ? 'color-mix(in srgb, var(--color-accent) 35%, transparent)' : 'var(--color-border)',
          background: rodando ? 'var(--color-accent-subtle)' : 'var(--color-surface)',
        }}
      >
        <div className="flex flex-wrap items-start gap-2 min-w-0">
          <span className="mt-1.5"><PontoAgente rodando={rodando} /></span>
          <div className="flex-1 min-w-[9rem]">
            <p className="text-sm font-medium" style={{ overflowWrap: 'anywhere' }}>{a.descricao || 'Agente sem descrição'}</p>
            <p className="text-xs text-[var(--color-text-secondary)] truncate">
              {a.tipo_agente || 'agente'}
              <span className="sr-only">{rodando ? ', rodando' : ', terminou'}</span>
            </p>
          </div>
          <div className="flex flex-wrap items-center justify-end gap-2 shrink-0">
            <ChipModelo modelo={a.modelo} modeloId={a.modelo_id} />
            <MedidorEsforco esforco={a.esforco} />
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-[var(--color-text-secondary)] pl-[18px]">
          <span className="inline-flex items-center gap-1 tabular-nums" title={rodando ? 'Rodando há' : 'Durou'}>
            <Timer size={12} aria-hidden="true" />
            {rodando ? dur : `durou ${dur}`}
          </span>
          <span className="inline-flex items-center gap-1 tabular-nums">
            <Wrench size={12} aria-hidden="true" />
            {a.ferramentas === 1 ? '1 ferramenta' : `${a.ferramentas ?? 0} ferramentas`}
          </span>
          {a.ultima_acao && (
            <span className="min-w-0 max-w-full truncate font-[family-name:var(--font-mono)]" title={a.ultima_acao}>
              {a.ultima_acao}
            </span>
          )}
        </div>
      </div>
      {no.filhos.length > 0 && (
        <ul className="ag-arvore" aria-label={`Sub-agentes de ${a.descricao || a.tipo_agente}`}>
          {no.filhos.map((f) => <NoAgente key={f.agente.id} no={f} agora={agora} />)}
        </ul>
      )}
    </li>
  );
}
