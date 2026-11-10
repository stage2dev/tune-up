import { useEffect, useState } from 'react';

/** Relogio de 1 s, so enquanto `ligado`. */
export function useAgora(ligado: boolean): number {
  const [agora, setAgora] = useState(() => Date.now());
  useEffect(() => {
    if (!ligado) return;
    setAgora(Date.now());
    const t = setInterval(() => setAgora(Date.now()), 1000);
    return () => clearInterval(t);
  }, [ligado]);
  return agora;
}
