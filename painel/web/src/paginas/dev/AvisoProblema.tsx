import { Link } from 'react-router';
import type { ResultadoErro } from './logica';

/** Mostra dentro do dialogo por que a acao nao comecou. 409 vira "ja esta rodando" com link. */
export function AvisoProblema({ problema }: { problema: ResultadoErro | null }) {
  if (!problema) return null;
  return (
    <div
      role="alert"
      className="rounded-lg border p-3 text-sm text-[var(--color-text)]"
      style={{
        background: 'color-mix(in srgb, var(--color-attention) 12%, transparent)',
        borderColor: 'color-mix(in srgb, var(--color-attention) 35%, transparent)',
      }}
    >
      {problema.tipo === 'conflito' ? (
        <>
          <p className="font-medium">Já está rodando.</p>
          <p className="break-words">{problema.texto}</p>
          <Link className="underline text-[var(--color-accent)]" to={`/execucoes/${encodeURIComponent(problema.execucaoId)}`}>
            Ver a execução
          </Link>
        </>
      ) : (
        <p className="break-words">{problema.texto}</p>
      )}
    </div>
  );
}
