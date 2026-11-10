// Funcoes puras da tela de chat (sem React), testadas em logica.test.ts.
import type { Acao, EventoExecucao, Execucao, Risco, StatusModelo } from '../../api/tipos';

export const GRUPO_CHAT = 'chat';
export const MAX_RESPOSTA = 6000;

const NOMES_MODELO: Record<string, string> = { fable: 'Fable', opus: 'Opus', sonnet: 'Sonnet', haiku: 'Haiku' };
const NOMES_ESFORCO: Record<string, string> = { low: 'baixo', medium: 'médio', high: 'alto', xhigh: 'muito alto', max: 'máximo' };

export const nomeModelo = (m: string): string => NOMES_MODELO[m] ?? m;
export const nomeEsforco = (e: string): string => NOMES_ESFORCO[e] ?? e;

// ---------------------------------------------------------------- niveis
export const acoesDoChat = (acoes: Acao[] | undefined): Acao[] => (acoes ?? []).filter((a) => a.grupo === GRUPO_CHAT);

/** Nivel salvo, se ainda existe; senao o primeiro do grupo. */
export function nivelInicial(niveis: Acao[], salvo: string | null): string | null {
  if (salvo && niveis.some((a) => a.id === salvo)) return salvo;
  return niveis[0]?.id ?? null;
}

/** Limite de letras do pedido: `max` do param `pedido` (padrao do contrato: 500). */
export function limitePedido(acao: Acao | undefined): number {
  return acao?.params.find((p) => p.nome === 'pedido')?.max ?? 500;
}

/** Contador so aparece perto do limite. */
export const mostrarContador = (tamanho: number, max: number): boolean => tamanho >= Math.floor(max * 0.8);

export const FRASE_CONFIRMAR: Record<Risco, string> = {
  leitura: 'O Claude só vai ler e responder. Nada é alterado.',
  rascunho: 'Isso vai escrever um rascunho para você revisar. Nada é publicado sozinho.',
  codigo: 'Isso vai mexer no código e abrir uma PR para você ver.',
  credito: 'Isso pode gastar crédito de um serviço pago.',
};

// ---------------------------------------------------------------- quem vai trabalhar
export type Escolha =
  | { tipo: 'padrao' } // modelos = [] : modelo padrao do CLI
  | { tipo: 'conferindo' } // ainda nao sabemos: nunca afirme um modelo
  | { tipo: 'ok'; modelo: string; semLicenca: string[] } // semLicenca = preferidos pulados por 'nao'
  | { tipo: 'incerto'; modelo: string; reserva: string }; // licenca nao pode ser conferida

/**
 * Modelo que vai rodar: o primeiro de `modelos` com status 'sim'; 'nao' cai no proximo;
 * o ultimo e a reserva e vale sempre. 'verificando' (ou status ainda nao chegou) = conferindo.
 */
export function escolherModelo(modelos: string[] | undefined, status: Record<string, StatusModelo> | undefined): Escolha {
  const lista = modelos ?? [];
  if (lista.length === 0) return { tipo: 'padrao' };
  const semLicenca: string[] = [];
  for (let i = 0; i < lista.length - 1; i++) {
    const m = lista[i];
    if (!status) return { tipo: 'conferindo' };
    const s = status[m];
    if (s === 'sim') return { tipo: 'ok', modelo: m, semLicenca };
    if (s === 'nao') {
      semLicenca.push(m);
      continue;
    }
    if (s === 'verificando') return { tipo: 'conferindo' };
    // 'nao_sei' ou sem status: nao da para afirmar qual sai.
    return { tipo: 'incerto', modelo: m, reserva: lista[lista.length - 1] };
  }
  return { tipo: 'ok', modelo: lista[lista.length - 1], semLicenca };
}

const juntarNomes = (ms: string[]): string => {
  const n = ms.map(nomeModelo);
  return n.length <= 1 ? (n[0] ?? '') : `${n.slice(0, -1).join(', ')} nem o ${n[n.length - 1]}`;
};

export interface QuemTrabalha {
  texto: string; // "Opus · esforço médio · 1 a 2 agentes"
  conferindo: boolean;
  aviso: string | null; // por que caiu na reserva, em palavras simples
}

export function quemVaiTrabalhar(acao: Pick<Acao, 'modelos' | 'esforco' | 'equipe'>, status: Record<string, StatusModelo> | undefined): QuemTrabalha {
  const e = escolherModelo(acao.modelos, status);
  let modelo: string;
  let aviso: string | null = null;
  if (e.tipo === 'conferindo') modelo = 'conferindo sua licença…';
  else if (e.tipo === 'padrao') modelo = 'modelo padrão';
  else if (e.tipo === 'incerto') {
    modelo = `${nomeModelo(e.modelo)} ou ${nomeModelo(e.reserva)}`;
    aviso = `Não consegui conferir se sua licença tem o ${nomeModelo(e.modelo)}; se não tiver, vai rodar com o ${nomeModelo(e.reserva)}.`;
  } else {
    modelo = nomeModelo(e.modelo);
    if (e.semLicenca.length) aviso = `Sua licença não tem o ${juntarNomes(e.semLicenca)}; vai rodar com o ${nomeModelo(e.modelo)}.`;
  }
  const partes = [modelo];
  if (acao.esforco) partes.push(`esforço ${nomeEsforco(acao.esforco)}`);
  if (acao.equipe) partes.push(acao.equipe);
  return { texto: partes.join(' · '), conferindo: e.tipo === 'conferindo', aviso };
}

/** Linha do cabecalho da conversa: modelo/esforco com que a sessao saiu ('' quando nao veio nada). */
export function comQueSaiu(e: Pick<Execucao, 'modelo' | 'esforco'>): string {
  const partes: string[] = [];
  if (e.modelo) partes.push(nomeModelo(e.modelo));
  if (e.esforco) partes.push(`esforço ${nomeEsforco(e.esforco)}`);
  return partes.join(' · ');
}

// ---------------------------------------------------------------- conversas
export const grupoDe = (e: Pick<Execucao, 'grupo' | 'area'>): string | undefined => e.grupo ?? e.area;

/** Execucoes do chat, mais novas primeiro. */
export function conversasDoChat(execucoes: Execucao[] | undefined): Execucao[] {
  const ms = (iso: string) => {
    const t = Date.parse(iso);
    return Number.isNaN(t) ? 0 : t;
  };
  return (execucoes ?? []).filter((e) => grupoDe(e) === GRUPO_CHAT).sort((a, b) => ms(b.iniciada_em) - ms(a.iniciada_em));
}

/** Para onde vai o clique numa execucao: chat abre a conversa; o resto, a tela tecnica. */
export function destinoDaExecucao(e: Pick<Execucao, 'id' | 'grupo' | 'area'>): string {
  const id = encodeURIComponent(e.id);
  return grupoDe(e) === GRUPO_CHAT ? `/conversa/${id}` : `/execucoes/${id}`;
}

/** Comeco do pedido numa linha so. */
export function comecoDoPedido(texto: string | undefined, max = 90): string {
  const t = (texto ?? '').replace(/\s+/g, ' ').trim();
  return t.length > max ? `${t.slice(0, max - 1).trimEnd()}…` : t;
}

// ---------------------------------------------------------------- itens da conversa
export type ItemConversa =
  | { tipo: 'dono'; chave: string; texto: string; ts: string }
  | { tipo: 'claude'; chave: string; texto: string; ts: string; erro: boolean }
  | { tipo: 'atividade'; chave: string; eventos: EventoExecucao[]; erros: number };

const ATIVIDADE = new Set(['ferramenta', 'subagente', 'resultado', 'sistema']);

/**
 * Monta os baloes: o 1o balao do dono e o `pedido` (o 1o evento 'usuario' e o prompt do servidor e fica de fora);
 * 'usuario' seguintes sao respostas do dono; 'assistente' sao falas do Claude; o resto vira um bloco de atividade
 * entre as falas.
 */
export function montarConversa(pedido: string | undefined, eventos: EventoExecucao[]): ItemConversa[] {
  const itens: ItemConversa[] = [];
  if (pedido) itens.push({ tipo: 'dono', chave: 'pedido', texto: pedido, ts: '' });
  let pulouPrompt = false;
  let bloco: Extract<ItemConversa, { tipo: 'atividade' }> | null = null;
  for (const ev of eventos) {
    if (ATIVIDADE.has(ev.tipo)) {
      if (!bloco) {
        bloco = { tipo: 'atividade', chave: `a${ev.n}`, eventos: [], erros: 0 };
        itens.push(bloco);
      }
      bloco.eventos.push(ev);
      if (ev.erro) bloco.erros++;
      continue;
    }
    if (ev.tipo === 'usuario' && !pulouPrompt) {
      pulouPrompt = true;
      continue;
    }
    bloco = null;
    if (ev.tipo === 'usuario') itens.push({ tipo: 'dono', chave: `u${ev.n}`, texto: ev.texto, ts: ev.ts });
    else if (ev.tipo === 'assistente') itens.push({ tipo: 'claude', chave: `c${ev.n}`, texto: ev.texto, ts: ev.ts, erro: !!ev.erro });
  }
  return itens;
}

/** Ultima acao de um bloco de atividade, curta, para a linha recolhida. */
export function ultimaAcao(eventos: EventoExecucao[]): string {
  const ev = eventos[eventos.length - 1];
  if (!ev) return '';
  return descreverEvento(ev);
}

export function descreverEvento(ev: EventoExecucao): string {
  const texto = ev.texto.replace(/\s+/g, ' ').trim();
  if (ev.tipo === 'ferramenta' || ev.tipo === 'subagente') return [ev.ferramenta, texto].filter(Boolean).join(': ');
  if (ev.tipo === 'resultado') return `Erro: ${texto}`;
  return texto;
}

export type PedacoTexto = { codigo: boolean; texto: string };

/** Separa blocos ``` (monoespacado) do texto normal. Bloco sem fechar vai ate o fim. */
export function pedacosDoTexto(texto: string): PedacoTexto[] {
  const partes = texto.split('```');
  const out: PedacoTexto[] = [];
  partes.forEach((p, i) => {
    const codigo = i % 2 === 1;
    // tira a linguagem da primeira linha do bloco (```ts)
    const t = codigo ? p.replace(/^[\w+-]*\n/, '').replace(/\n$/, '') : p;
    if (t.trim()) out.push({ codigo, texto: codigo ? t : t.replace(/^\n+|\n+$/g, '') });
  });
  return out;
}
