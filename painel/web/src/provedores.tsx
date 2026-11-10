import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState, type ReactNode } from 'react';
import { ProvedorAvisos } from './componentes/Avisos';
import { ProvedorTema } from './tema/tema';

/** Busca com cache + tema + avisos. Envolve o app inteiro (veja main.tsx). */
export function Provedores({ children }: { children: ReactNode }) {
  const [cliente] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { retry: 1, staleTime: 2000, refetchOnWindowFocus: true },
        },
      }),
  );
  return (
    <QueryClientProvider client={cliente}>
      <ProvedorTema>
        <ProvedorAvisos>{children}</ProvedorAvisos>
      </ProvedorTema>
    </QueryClientProvider>
  );
}
