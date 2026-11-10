// Ganchos de busca (TanStack Query v5). Regra de tela: enquanto carrega, use `isPending`
// (nunca isLoading) para mostrar esqueleto; so mostre "vazio" quando !isPending && !isError.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiGet, apiPost, ErroApi } from './cliente';
import type { Acao, Acompanhamento, DadosModulo, EstadoPainel, Eventos, Execucao, ListaModulos, ReqAcaoModulo, RespAcaoModulo, Sessao } from './tipos';
import { obterSessao } from './cliente';
import { buscarEventos, intervaloEventos, type EventosCache } from './eventos';

export const chaves = {
  sessao: ['sessao'] as const,
  estado: ['estado'] as const,
  acoes: ['acoes'] as const,
  execucoes: ['execucoes'] as const,
  eventos: (id: string) => ['eventos', id] as const,
  modulos: ['modulos'] as const,
  modulo: (id: string) => ['modulo', id] as const,
  acompanhamento: ['acompanhamento'] as const,
};

export const useSessao = () => useQuery<Sessao>({ queryKey: chaves.sessao, queryFn: obterSessao, staleTime: Infinity });

export const useEstado = () =>
  useQuery({ queryKey: chaves.estado, queryFn: () => apiGet<EstadoPainel>('/api/estado'), refetchInterval: 5000 });

export const useAcoes = () =>
  useQuery({ queryKey: chaves.acoes, queryFn: () => apiGet<{ acoes: Acao[] }>('/api/acoes').then((r) => r.acoes), staleTime: 60_000 });

/** Lista de execucoes, atualizada a cada 3 s. */
export const useExecucoes = () =>
  useQuery({
    queryKey: chaves.execucoes,
    queryFn: () => apiGet<{ execucoes: Execucao[] }>('/api/execucoes').then((r) => r.execucoes),
    refetchInterval: 3000,
  });

/** Modulos habilitados no pacote do projeto (menu lateral). Sem modulos, a lista vem vazia. */
export const useModulos = () =>
  useQuery({ queryKey: chaves.modulos, queryFn: () => apiGet<ListaModulos>('/api/modulos'), refetchInterval: 30_000 });

/** Uma tela de modulo (alertas, abas e blocos). */
export const useModulo = (id: string | undefined) =>
  useQuery({
    queryKey: chaves.modulo(id ?? ''),
    enabled: !!id,
    queryFn: () => apiGet<DadosModulo>(`/api/modulos/${encodeURIComponent(id ?? '')}`),
    refetchInterval: 15_000,
  });

/** Chama uma acao do modulo (POST) e, se der certo, puxa o modulo de novo sem o cache do servidor. */
export async function postarAcao(id: string, req: ReqAcaoModulo): Promise<RespAcaoModulo> {
  const r = await apiPost<RespAcaoModulo | null>(`/api/modulos/${encodeURIComponent(id)}/acao`, req);
  if (r?.ok !== true) throw new ErroApi('O painel não confirmou que a ação foi feita.', 502); // 2xx sem { ok: true } nao e sucesso
  return r;
}

export function useAcaoModulo(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (req: ReqAcaoModulo) => postarAcao(id, req),
    onSuccess: () => {
      const chave = chaves.modulo(id);
      void qc
        .cancelQueries({ queryKey: chave })
        .then(() => qc.fetchQuery({ queryKey: chave, staleTime: 0, queryFn: () => apiGet<DadosModulo>(`/api/modulos/${encodeURIComponent(id)}?fresco=1`) }))
        .catch(() => undefined); // a acao deu certo; se a releitura falhar, a tela avisa "nao foi possivel atualizar"
    },
  });
}

export const useAcompanhamento = () =>
  useQuery({ queryKey: chaves.acompanhamento, queryFn: () => apiGet<Acompanhamento>('/api/acompanhamento'), refetchInterval: 10_000 });

/**
 * Eventos de uma execucao. Cada chamada pede so o que e novo (desde=proximo) e
 * junta no cache; cada busca segue pedindo ate o `proximo` parar de andar. Para de
 * buscar so quando a execucao terminou E o fim do arquivo ja chegou.
 */
export function useEventos(id: string | undefined) {
  const qc = useQueryClient();
  return useQuery({
    queryKey: chaves.eventos(id ?? ''),
    enabled: !!id,
    refetchInterval: (q) => intervaloEventos(q.state.data),
    // Pede pedaco atras de pedaco ate o fim, mesmo com a execucao ja acabada.
    queryFn: (): Promise<EventosCache> =>
      buscarEventos(
        (desde) => apiGet<Eventos>(`/api/execucoes/${encodeURIComponent(id ?? '')}/eventos?desde=${desde}`),
        qc.getQueryData<EventosCache>(chaves.eventos(id ?? '')),
      ),
  });
}

/** POST /api/execucoes. O erro 409 chega como ErroApi com execucaoId. */
export function useIniciarExecucao() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (corpo: { acao: string; params: Record<string, string> }) =>
      apiPost<{ execucao: Execucao }>('/api/execucoes', corpo).then((r) => r.execucao),
    onSuccess: () => qc.invalidateQueries({ queryKey: chaves.execucoes }),
  });
}

export function usePararExecucao() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiPost<{ ok: boolean }>(`/api/execucoes/${encodeURIComponent(id)}/parar`),
    onSuccess: () => qc.invalidateQueries({ queryKey: chaves.execucoes }),
  });
}

export function useAbrirNoTerminal() {
  return useMutation({
    mutationFn: (id: string) => apiPost<{ ok: boolean; comando: string }>(`/api/execucoes/${encodeURIComponent(id)}/abrir`),
  });
}
