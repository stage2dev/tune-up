// Rascunho compartilhado de uma aba: os blocos "cores" e "opcoes" escrevem a escolha na hora, a "previa" le.
// Quem escreve tambem apaga: quando o comando falha ou quando o valor novo volta do servidor.
import { createContext, useContext, useMemo, useState, type ReactNode } from 'react';
import { comRascunho, semRascunho, type Rascunho, type ValorRascunho } from './marca';

interface Ctx { rascunho: Rascunho; por: (campo: string, v: ValorRascunho) => void; tirar: (campo: string) => void }

const Contexto = createContext<Ctx>({ rascunho: {}, por: () => {}, tirar: () => {} }); // fora do provedor: nada e compartilhado

export function ProvedorRascunho({ children }: { children: ReactNode }) {
  const [rascunho, setRascunho] = useState<Rascunho>({});
  const mudar = useMemo(() => ({ // estaveis: podem entrar em dependencias de efeito
    por: (campo: string, v: ValorRascunho) => setRascunho((r) => comRascunho(r, campo, v)),
    tirar: (campo: string) => setRascunho((r) => semRascunho(r, campo)),
  }), []);
  const valor = useMemo<Ctx>(() => ({ rascunho, ...mudar }), [rascunho, mudar]);
  return <Contexto.Provider value={valor}>{children}</Contexto.Provider>;
}

export const useRascunho = (): Ctx => useContext(Contexto);
