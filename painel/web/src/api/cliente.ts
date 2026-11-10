// Cliente da API do painel.
// - pega o token em /api/sessao (uma vez; renova sozinho se o servidor reiniciou)
// - manda X-Painel-Token e Content-Type em todo POST
// - transforma {erro:"texto"} em ErroApi com mensagem simples
import type { Sessao } from './tipos';

export class ErroApi extends Error {
  status: number;
  /** Vem no 409: id da execucao que ja esta rodando. */
  execucaoId?: string;
  constructor(mensagem: string, status: number, execucaoId?: string) {
    super(mensagem);
    this.name = 'ErroApi';
    this.status = status;
    this.execucaoId = execucaoId;
  }
}

const MSG_SEM_SERVIDOR = 'Não consegui falar com o painel. Ele está ligado?';

let sessaoEmCache: Promise<Sessao> | null = null;

export function esquecerSessao(): void {
  sessaoEmCache = null;
}

async function lerJson(resp: Response): Promise<unknown> {
  const texto = await resp.text();
  if (!texto) return null;
  try {
    return JSON.parse(texto) as unknown;
  } catch {
    return null;
  }
}

function erroDe(resp: Response, corpo: unknown): ErroApi {
  const obj = (corpo && typeof corpo === 'object' ? corpo : {}) as Record<string, unknown>;
  const msg = typeof obj.erro === 'string' && obj.erro ? obj.erro : `Algo deu errado (código ${resp.status}).`;
  const id = typeof obj.execucao_id === 'string' ? obj.execucao_id : undefined;
  return new ErroApi(msg, resp.status, id);
}

async function pedir(url: string, init?: RequestInit): Promise<{ resp: Response; corpo: unknown }> {
  let resp: Response;
  try {
    resp = await fetch(url, init);
  } catch {
    throw new ErroApi(MSG_SEM_SERVIDOR, 0);
  }
  return { resp, corpo: await lerJson(resp) };
}

/** GET /api/sessao. Fica em cache; o token nasce a cada subida do servidor. */
export function obterSessao(): Promise<Sessao> {
  if (!sessaoEmCache) {
    const p = pedir('/api/sessao').then(({ resp, corpo }) => {
      if (!resp.ok) throw erroDe(resp, corpo);
      const s = corpo as Sessao | null;
      if (!s || typeof s.token !== 'string') throw new ErroApi('Resposta estranha do painel.', resp.status);
      return s;
    });
    sessaoEmCache = p;
    p.catch(() => {
      if (sessaoEmCache === p) sessaoEmCache = null;
    });
  }
  return sessaoEmCache;
}

export async function apiGet<T>(caminho: string): Promise<T> {
  const { resp, corpo } = await pedir(caminho);
  if (!resp.ok) throw erroDe(resp, corpo);
  return corpo as T;
}

async function enviar(caminho: string, corpo: unknown, tentarDeNovo: boolean): Promise<unknown> {
  const sessao = await obterSessao();
  const { resp, corpo: resposta } = await pedir(caminho, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Painel-Token': sessao.token },
    body: JSON.stringify(corpo ?? {}),
  });
  // Token velho (servidor reiniciou): pega outro e tenta uma vez.
  if (resp.status === 403 && tentarDeNovo) {
    esquecerSessao();
    return enviar(caminho, corpo, false);
  }
  if (!resp.ok) throw erroDe(resp, resposta);
  return resposta;
}

export async function apiPost<T>(caminho: string, corpo?: unknown): Promise<T> {
  return (await enviar(caminho, corpo, true)) as T;
}
