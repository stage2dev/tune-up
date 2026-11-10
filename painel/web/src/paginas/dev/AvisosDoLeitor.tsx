/** Avisos do leitor dos planos: recolhidos, porque podem ser dezenas. */
export function AvisosDoLeitor({ avisos }: { avisos: string[] }) {
  if (avisos.length === 0) return null;
  return (
    <details className="mb-3 text-xs text-[var(--color-text-secondary)]">
      <summary className="cursor-pointer">{avisos.length === 1 ? '1 aviso sobre os planos' : `${avisos.length} avisos sobre os planos`}</summary>
      <ul className="mt-2 grid grid-cols-1 gap-1 list-disc pl-4">
        {avisos.map((a, i) => (
          <li key={i} className="break-words">
            {a}
          </li>
        ))}
      </ul>
    </details>
  );
}
