// Logica das acoes: filtrar, validar parametros e disparar. Sem React, para testar sem tela.
import { ErroApi } from '../../api/cliente';
import type { Acao, Execucao, ParamAcao, Risco } from '../../api/tipos';

export const ROTULO_RISCO: Record<Risco, string> = {
  leitura: 'Só leitura',
  rascunho: 'Rascunho',
  codigo: 'Mexe no código',
  credito: 'Pode gastar crédito',
};

export const TEXTO_RISCO: Record<Risco, string> = {
  leitura: 'Só olha e anota. Não muda nada.',
  rascunho: 'Escreve rascunhos em arquivos. Nada é publicado.',
  codigo: 'Pode mudar arquivos de código.',
  credito: 'Pode usar crédito de uma ferramenta (ex.: pesquisa de SEO). Nunca verba de anúncio.',
};

/** Ações de um grupo, na ordem em que o servidor mandou. */
export function acoesDoGrupo(acoes: Acao[], grupo: string): Acao[] {
  return acoes.filter((a) => a.grupo === grupo);
}

/** Valores iniciais do formulário: 'escolha' obrigatória começa vazia de propósito (a pessoa decide). */
export function valoresIniciais(params: ParamAcao[]): Record<string, string> {
  const v: Record<string, string> = {};
  for (const p of params) v[p.nome] = '';
  return v;
}

/** Texto do erro de cada campo com problema; objeto vazio = tudo certo. */
export function validarParams(params: ParamAcao[], valores: Record<string, string>): Record<string, string> {
  const erros: Record<string, string> = {};
  for (const p of params) {
    const v = (valores[p.nome] ?? '').trim();
    if (!v) {
      if (p.obrigatorio) erros[p.nome] = p.tipo === 'escolha' ? 'Escolha uma opção.' : 'Preencha este campo.';
      continue;
    }
    if (p.tipo === 'escolha' && !(p.opcoes ?? []).includes(v)) erros[p.nome] = 'Escolha uma das opções.';
    const max = p.max ?? 500;
    if (p.tipo === 'texto' && v.length > max) erros[p.nome] = `Máximo de ${max} letras.`;
  }
  return erros;
}

/** Corpo do POST: só os campos preenchidos, sem espaços nas pontas. */
export function montarParams(params: ParamAcao[], valores: Record<string, string>): Record<string, string> {
  const out: Record<string, string> = {};
  for (const p of params) {
    const v = (valores[p.nome] ?? '').trim();
    if (v) out[p.nome] = v;
  }
  return out;
}

/** Precisa abrir o diálogo antes de rodar? (pede confirmação ou tem campo para preencher) */
export function precisaDeDialogo(a: Acao): boolean {
  return a.confirmar || a.params.length > 0;
}

export type ResultadoDisparo =
  | { tipo: 'ok'; execucao: Execucao }
  | { tipo: 'ja_rodando'; execucaoId: string | null; mensagem: string }
  | { tipo: 'erro'; mensagem: string };

/**
 * Dispara a ação. `iniciar` é o POST /api/execucoes (a mutação do react-query).
 * 409 não é falha: já existe uma execução igual, e a tela leva até ela.
 */
export async function dispararAcao(
  iniciar: (corpo: { acao: string; params: Record<string, string> }) => Promise<Execucao>,
  acao: Acao,
  valores: Record<string, string>,
): Promise<ResultadoDisparo> {
  const erros = validarParams(acao.params, valores);
  const primeiro = Object.values(erros)[0];
  if (primeiro) return { tipo: 'erro', mensagem: primeiro };
  try {
    const execucao = await iniciar({ acao: acao.id, params: montarParams(acao.params, valores) });
    return { tipo: 'ok', execucao };
  } catch (e) {
    if (e instanceof ErroApi && e.status === 409) {
      return { tipo: 'ja_rodando', execucaoId: e.execucaoId ?? null, mensagem: e.message };
    }
    return { tipo: 'erro', mensagem: e instanceof Error && e.message ? e.message : 'Não consegui começar.' };
  }
}

export const caminhoDaExecucao = (id: string) => `/execucoes/${encodeURIComponent(id)}`;
