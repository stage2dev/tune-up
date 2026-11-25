// Linha de custo do cartao da sessao: tokens, contexto maximo, % por modelo e US$ estimado (sempre rotulado).
import type { EstadoCusto } from '../../api/custo';
import { compacto, dolares, porcento } from '../modulo/formato';
import { corModelo, rotuloModelo } from './logica';

const TITULO_ESTIMATIVA =
  'Estimativa feita com uma tabela fixa de preços, não é a fatura. Inclui os sub-agentes. ' +
  'O contexto máximo é só o da conversa principal. As porcentagens são do custo estimado.';

const CLASSE = 'flex flex-wrap items-center gap-x-3 gap-y-1 text-xs tabular-nums text-[var(--color-text-secondary)]';

export function CustoSessao({ estado }: { estado: EstadoCusto }) {
  if (estado.tipo === 'calculando') return <p className={CLASSE} role="status">calculando custo…</p>;
  if (estado.tipo === 'erro') return <p className={CLASSE} title="Não consegui ler o custo desta sessão agora.">custo não lido</p>;
  const c = estado.custo;
  if (!c.encontrada) return <p className={CLASSE} title="O arquivo desta sessão não foi achado, então não há como estimar.">custo não encontrado</p>;
  const total = c.tokens?.total ?? null;
  return (
    <p className={CLASSE} title={TITULO_ESTIMATIVA}>
      <span>{total === null ? 'tokens: sem dado' : `${compacto(total)} tokens`}</span>
      <span>contexto máx. {compacto(c.contexto_maximo)}</span>
      {c.modelos.length > 0 && (
        <span>
          {c.modelos.map((m, i) => (
            <span key={m.modelo}>
              {i > 0 && ' · '}
              <span style={{ color: corModelo(m.modelo) }}>{rotuloModelo(m.modelo)}</span>
              {m.pct !== null && ` ${porcento(m.pct)}`}
            </span>
          ))}
        </span>
      )}
      <span className="font-medium text-[var(--color-text)]">
        {c.usd === null ? 'sem preço' : `${c.usd_incompleto ? 'mín. ' : ''}≈ ${dolares(c.usd)} (estimativa)`}
      </span>
      {c.usd !== null && c.usd_incompleto && <span title="Algum modelo desta sessão não está na tabela de preços; o valor soma só os que têm preço.">incompleto</span>}
      {c.parcial && <span title="Só parte do histórico desta sessão foi lida; os números podem estar abaixo do real.">parcial</span>}
    </p>
  );
}
