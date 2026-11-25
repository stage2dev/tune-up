// Contrato de GET /api/custo?sessao=<uuid>&sessao=<uuid>... (custo.py). Só leitura.
//
// Regras
// - 0 a 60 sessionIds (UUID completo); repetidos respondem uma vez; zero -> sessoes [].
//   Mais de 60 ou id inválido -> 400 {"erro": "Sessão inválida."}.
// - Os valores em US$ são ESTIMATIVA (tabela de preços assumida em custo.py), nunca o preço oficial.
// - Soma a conversa principal e os subagentes; contexto_maximo é só da conversa principal.
// - Nunca leva texto de mensagem, caminho nem título.

export interface Custo {
  estimativa: true;
  sessoes: CustoSessao[];
}

export interface CustoSessao {
  sessao_id: string;
  encontrada: boolean; // false: sem transcrito; os números abaixo ficam null e modelos []
  parcial: boolean; // algum arquivo não pôde ser lido, ou o limite de arquivos de subagente foi atingido
  tokens: { entrada: number; saida: number; cache_escrita: number; cache_leitura: number; total: number } | null;
  contexto_maximo: number | null; // maior entrada+cache_escrita+cache_leitura de uma mensagem; null sem uso
  subagentes: number; // arquivos somados
  usd: number | null; // estimado; null quando nenhum modelo tem preço
  usd_incompleto: boolean; // true: algum modelo está fora da tabela de preços
  modelos: Array<{ modelo: string; tokens: number; usd: number | null; pct: number | null }>; // por usd desc
}
