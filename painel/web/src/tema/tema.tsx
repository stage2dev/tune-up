// Adaptado de OpenJarvis (Apache-2.0), frontend/src/main.tsx:12-24 (aplicar tema por classe em <html>); alterado
// Tema claro/escuro/sistema com ciclo de tres estados e salvamento tolerante a falha.
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';

export type Tema = 'claro' | 'escuro' | 'sistema';
const CHAVE = 'painel-tema';
const CICLO: Tema[] = ['claro', 'escuro', 'sistema'];

function lerSalvo(): Tema {
  try {
    const v = localStorage.getItem(CHAVE);
    if (v === 'claro' || v === 'escuro' || v === 'sistema') return v;
  } catch {
    /* sem armazenamento: usa o sistema */
  }
  return 'sistema';
}

export function aplicarTema(t: Tema): void {
  const raiz = document.documentElement;
  raiz.classList.toggle('dark', t === 'escuro');
  raiz.classList.toggle('light', t === 'claro');
}

/** Chame antes de renderizar, para nao piscar. */
export function iniciarTema(): void {
  aplicarTema(lerSalvo());
}

interface Ctx {
  tema: Tema;
  alternar: () => void;
}
const Contexto = createContext<Ctx | null>(null);

export function ProvedorTema({ children }: { children: ReactNode }) {
  const [tema, setTema] = useState<Tema>(lerSalvo);
  useEffect(() => aplicarTema(tema), [tema]);
  const alternar = useCallback(() => {
    setTema((atual) => {
      const novo = CICLO[(CICLO.indexOf(atual) + 1) % CICLO.length];
      try {
        localStorage.setItem(CHAVE, novo);
      } catch {
        /* tudo bem */
      }
      return novo;
    });
  }, []);
  const valor = useMemo(() => ({ tema, alternar }), [tema, alternar]);
  return <Contexto.Provider value={valor}>{children}</Contexto.Provider>;
}

export function useTema(): Ctx {
  const c = useContext(Contexto);
  if (!c) throw new Error('useTema fora do ProvedorTema');
  return c;
}
