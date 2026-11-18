// Ganchos de busca (TanStack Query v5). Regra de tela: enquanto carrega, use `isPending`
// (nunca isLoading) para mostrar esqueleto; so mostre "vazio" quando !isPending && !isError.
import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query';
import { apiGet, apiPost, ErroApi } from './cliente';
import type { Acao, Acompanhamento, DadosModulo, EstadoPainel, Eventos, Execucao, ListaEmbutidos, ListaModulos, ReqAcaoModulo, RespAcaoModulo, RespHabilidades, RespModelos, RespMudarPlugin, RespPlugins, Sessao } from './tipos';
import { obterSessao } from './cliente';
import { buscarEventos, intervaloEventos, type EventosCache } from './eventos';

export const chaves = {
  sessao: ['sessao'] as const,
  estado: ['estado'] as const,
  acoes: ['acoes'] as const,
  execucoes: ['execucoes'] as const,
  eventos: (id: string) => ['eventos', id] as const,
  /** Eventos com as falas inteiras (?inteiro=1, tela de conversa). Chave propria: nao mistura com o texto cortado. */
  eventosInteiro: (id: string) => ['eventos-inteiro', id] as const,
  modelos: ['modelos'] as const,
  habilidades: ['habilidades'] as const,
  modulos: ['modulos'] as const,
  embutidos: ['embutidos'] as const,
  plugins: ['plugins'] as const,
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

/** Partes extras embutidas (tela Modulos), com o estado ligado/desligado. */
export const useEmbutidos = () =>
  useQuery({ queryKey: chaves.embutidos, queryFn: () => apiGet<ListaEmbutidos>('/api/embutidos').then((r) => r.embutidos) });

/** Liga/desliga uma parte extra. Usa a lista devolvida pelo servidor (sem otimismo) e renova menu e botoes. */
export function useLigarEmbutido() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ligado }: { id: string; ligado: boolean }) =>
      apiPost<ListaEmbutidos & { ok: boolean }>(`/api/embutidos/${encodeURIComponent(id)}`, { ligado }),
    onSuccess: (r) => {
      qc.setQueryData(chaves.embutidos, r.embutidos);
      void qc.invalidateQueries({ queryKey: chaves.modulos });
      void qc.invalidateQueries({ queryKey: chaves.acoes });
    },
  });
}

/** Plugins do Claude Code (secao da tela Modulos). Sem releitura automatica: o arquivo so muda por acao da pessoa. */
export const usePlugins = () =>
  useQuery({ queryKey: chaves.plugins, queryFn: () => apiGet<RespPlugins>('/api/plugins') });

/** Liga/desliga um plugin no settings do usuario. Sem otimismo: a lista so muda com a resposta do servidor. */
export function useMudarPlugin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) => apiPost<RespMudarPlugin>('/api/plugins', { id, enabled }),
    onSuccess: (r) => qc.setQueryData<RespPlugins>(chaves.plugins, (antes) => ({ plugins: r.plugins, aviso: antes?.aviso ?? null })),
  });
}

/** Intervalo de releitura do modulo em ms: atualizar_em (s) preso em 2..60; sem numero, 15 s. */
export function intervaloDeAtualizacao(v: unknown): number {
  if (typeof v !== 'number' || !Number.isFinite(v)) return 15_000;
  return Math.round(Math.min(60, Math.max(2, v)) * 1000);
}

/** Uma tela de modulo (alertas, abas e blocos). Relê no ritmo de `atualizar_em` (2..60 s; sem ele, 15 s);
 *  com a aba do navegador escondida, para (refetchIntervalInBackground: false). */
const buscarModulo = (id: string) => apiGet<DadosModulo>(`/api/modulos/${encodeURIComponent(id)}`);

export const useModulo = (id: string | undefined) =>
  useQuery({
    queryKey: chaves.modulo(id ?? ''),
    enabled: !!id,
    queryFn: () => buscarModulo(id ?? ''),
    refetchInterval: (q) => intervaloDeAtualizacao(q.state.data?.atualizar_em),
    refetchIntervalInBackground: false,
  });

/** Chama uma acao do modulo (POST) e, se der certo, puxa o modulo de novo sem o cache do servidor. */
export async function postarAcao(id: string, req: ReqAcaoModulo): Promise<RespAcaoModulo> {
  const r = await apiPost<RespAcaoModulo | null>(`/api/modulos/${encodeURIComponent(id)}/acao`, req);
  if (r?.ok !== true) throw new ErroApi('O painel não confirmou que a ação foi feita.', 502); // 2xx sem { ok: true } nao e sucesso
  if (r.resultado?.feito === false) { // o modulo recusou (selo vermelho, marca mudou...): nao e "Feito."
    const m = r.resultado.mensagem;
    throw new ErroApi(typeof m === 'string' && m ? m : 'A ação não foi feita.', 409);
  }
  return r;
}

/** Rele o modulo sem o cache do servidor (depois de uma acao ou de um envio que deu certo). */
export function relerModulo(qc: ReturnType<typeof useQueryClient>, id: string): void {
  const chave = chaves.modulo(id);
  void qc
    .cancelQueries({ queryKey: chave })
    .then(() => qc.fetchQuery({ queryKey: chave, staleTime: 0, queryFn: () => apiGet<DadosModulo>(`/api/modulos/${encodeURIComponent(id)}?fresco=1`) }))
    .catch(() => undefined); // a acao deu certo; se a releitura falhar, a tela avisa "nao foi possivel atualizar"
}

export function useAcaoModulo(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (req: ReqAcaoModulo) => postarAcao(id, req),
    onSuccess: () => relerModulo(qc, id),
  });
}

export const useAcompanhamento = () =>
  useQuery({ queryKey: chaves.acompanhamento, queryFn: () => apiGet<Acompanhamento>('/api/acompanhamento'), refetchInterval: 10_000 });

/**
 * Eventos de uma execucao. Cada chamada pede so o que e novo (desde=proximo) e
 * junta no cache; cada busca segue pedindo ate o `proximo` parar de andar. Para de
 * buscar so quando a execucao terminou E o fim do arquivo ja chegou.
 */
export function useEventos(id: string | undefined, inteiro = false) {
  const qc = useQueryClient();
  const chave = inteiro ? chaves.eventosInteiro(id ?? '') : chaves.eventos(id ?? '');
  const extra = inteiro ? '&inteiro=1' : '';
  return useQuery({
    queryKey: chave,
    enabled: !!id,
    refetchInterval: (q) => intervaloEventos(q.state.data),
    // Pede pedaco atras de pedaco ate o fim, mesmo com a execucao ja acabada.
    queryFn: (): Promise<EventosCache> =>
      buscarEventos(
        (desde) => apiGet<Eventos>(`/api/execucoes/${encodeURIComponent(id ?? '')}/eventos?desde=${desde}${extra}`),
        qc.getQueryData<EventosCache>(chave),
      ),
  });
}

/** GET /api/modelos. Busca de novo a cada 4 s so enquanto algum modelo estiver 'verificando'. */
export const useModelos = () =>
  useQuery({
    queryKey: chaves.modelos,
    queryFn: () => apiGet<RespModelos>('/api/modelos').then((r) => r.modelos ?? {}),
    refetchInterval: (q) => (Object.values(q.state.data ?? {}).includes('verificando') ? 4000 : false),
  });

/** GET /api/habilidades: lista de skills do chat. Poucas buscas (cache de 5 min); 404 = servidor antigo, sem repetir. */
export const useHabilidades = () =>
  useQuery({
    queryKey: chaves.habilidades,
    queryFn: () => apiGet<RespHabilidades>('/api/habilidades'),
    staleTime: 5 * 60_000,
    retry: (n, e) => !(e instanceof ErroApi && e.status === 404) && n < 2,
  });

/** Erro 400 ao enviar com skills: a lista pode ter mudado; busca de novo para a tela atualizar sozinha. */
function atualizarSeHabilidadeInvalida(qc: QueryClient, e: unknown, habilidades?: string[]) {
  if (habilidades?.length && e instanceof ErroApi && e.status === 400) void qc.invalidateQueries({ queryKey: chaves.habilidades });
}

/** POST /api/execucoes/{id}/responder: continua a mesma sessao. */
export function useResponder() {
  const qc = useQueryClient();
  return useMutation({
    onError: (e, v) => atualizarSeHabilidadeInvalida(qc, e, v.habilidades),
    mutationFn: ({ id, texto, interromper, habilidades }: { id: string; texto: string; interromper?: boolean; habilidades?: string[] }) =>
      apiPost<{ execucao: Execucao }>(`/api/execucoes/${encodeURIComponent(id)}/responder`, {
        texto,
        ...(interromper ? { interromper: true } : {}),
        ...(habilidades?.length ? { habilidades } : {}),
      }).then((r) => r.execucao),
    onSuccess: (e) => {
      // Troca a execucao na lista ja (sem esperar os 3 s) e religa a busca de eventos, que tinha parado no fim.
      qc.setQueryData<Execucao[]>(chaves.execucoes, (l) => l?.map((x) => (x.id === e.id ? e : x)));
      qc.setQueryData<EventosCache>(chaves.eventosInteiro(e.id), (d) => (d ? { ...d, estado: e.estado } : d));
      void qc.invalidateQueries({ queryKey: chaves.execucoes });
      void qc.invalidateQueries({ queryKey: chaves.eventosInteiro(e.id) });
    },
  });
}

/** POST /api/execucoes. O erro 409 chega como ErroApi com execucaoId. */
export function useIniciarExecucao() {
  const qc = useQueryClient();
  return useMutation({
    onError: (e, v) => atualizarSeHabilidadeInvalida(qc, e, v.habilidades),
    mutationFn: (corpo: { acao: string; params: Record<string, string>; habilidades?: string[] }) =>
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
