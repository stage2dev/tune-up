// Adaptado de OpenJarvis (Apache-2.0), frontend/src/index.css (.data-skeleton); alterado
/** Bloco cinza animado para "carregando". Use enquanto isPending. */
export function Esqueleto({ className = 'h-4 w-full' }: { className?: string }) {
  return <div className={`data-skeleton ${className}`} aria-hidden="true" />;
}

/** Varios cartoes de esqueleto, para uma pagina inteira carregando. */
export function EsqueletoPagina({ cartoes = 3 }: { cartoes?: number }) {
  return (
    <div role="status" aria-label="Carregando" className="grid gap-3">
      <span className="sr-only">Carregando…</span>
      {Array.from({ length: cartoes }, (_, i) => (
        <div key={i} className="hud-panel p-4 grid gap-3">
          <Esqueleto className="h-4 w-1/3" />
          <Esqueleto className="h-3 w-full" />
          <Esqueleto className="h-3 w-2/3" />
        </div>
      ))}
    </div>
  );
}
