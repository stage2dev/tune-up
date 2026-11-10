import { AlertTriangle } from 'lucide-react';
import { Botao } from './Botao';

/** Erro de carregamento, com botao "Tentar de novo" (passe refetch). */
export function Erro({ erro, aoTentar }: { erro: unknown; aoTentar?: () => void }) {
  const msg = erro instanceof Error && erro.message ? erro.message : 'Algo deu errado.';
  return (
    <div
      role="alert"
      className="flex items-start gap-3 p-4 rounded-lg border"
      style={{
        background: 'color-mix(in srgb, var(--color-error) 8%, transparent)',
        borderColor: 'color-mix(in srgb, var(--color-error) 25%, transparent)',
      }}
    >
      <AlertTriangle size={18} aria-hidden="true" className="shrink-0 mt-0.5 text-[var(--color-error)]" />
      <div className="flex-1 min-w-0">
        <p className="text-sm break-words">{msg}</p>
        {aoTentar && (
          <Botao variante="secundario" className="mt-2 h-8" onClick={aoTentar}>
            Tentar de novo
          </Botao>
        )}
      </div>
    </div>
  );
}
