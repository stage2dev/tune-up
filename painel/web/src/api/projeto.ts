// Nome do projeto para o cabecalho: vem de /api/estado (campo projeto.nome); sem ele, "tune-up".
export const NOME_PADRAO = 'tune-up';

export function nomeDoProjeto(estado: unknown): string {
  const p = (estado as { projeto?: { nome?: unknown } } | null | undefined)?.projeto;
  return typeof p?.nome === 'string' && p.nome.trim() ? p.nome.trim() : NOME_PADRAO;
}
