// Funcoes puras da caixa de baixo da conversa e das perguntas com opcoes (testadas em caixa.test.ts).
import type { EstadoExecucao, PerguntaChat } from '../../api/tipos';

export type ModoCaixa = 'responder' | 'interromper' | 'parar' | 'esperando' | 'comecando' | 'ocupado' | 'fechada' | 'sumiu';

export interface EstadoCaixa {
  modo: ModoCaixa;
  /** Caixa de texto aceita digitar. */
  habilitada: boolean;
  /** Texto do botao principal; null = sem botao. */
  botao: string | null;
  /** O envio vai com interromper: true. */
  interromper: boolean;
  /** Linha pequena acima da caixa. */
  dica: string | null;
  placeholder: string;
}

const ESCREVA = 'Escreva aqui…';

export interface SituacaoCaixa {
  estado: EstadoExecucao;
  pode_responder?: boolean;
  pode_interromper?: boolean;
  /** Veio `execucao.pergunta`. */
  temPergunta?: boolean;
  /** A espera e um pedido preso no terminal (permissao): escrever aqui cancela o pedido, nao aprova. */
  espera_terminal?: boolean;
}

/**
 * O que a caixa mostra. `pode_responder` vence sempre (em qualquer estado, inclusive precisa_de_voce com
 * pergunta escrita): caixa normal, sem interromper. `interromper: true` so com pode_responder false e
 * pode_interromper true. `pode_interromper` ausente (servidor antigo) = 'ocupado', nunca "comecando" para sempre.
 */
export function estadoCaixa(sit: SituacaoCaixa, textoVazio: boolean): EstadoCaixa {
  const { estado, pode_responder: podeResponder, pode_interromper: podeInterromper } = sit;
  const base = { habilitada: false, botao: null, interromper: false, dica: null, placeholder: ESCREVA };
  if (podeResponder) {
    const perguntou = estado === 'precisa_de_voce' || !!sit.temPergunta;
    return {
      ...base,
      modo: 'responder',
      habilitada: true,
      botao: 'Responder',
      dica: perguntou ? 'O Claude fez uma pergunta. Responda aqui embaixo.' : null,
      placeholder: perguntou ? 'Escreva sua resposta aqui…' : 'Quer pedir mais alguma coisa? Escreva aqui.',
    };
  }
  if (estado === 'sumiu') return { ...base, modo: 'sumiu', placeholder: 'Esta conversa acabou.' };
  if (estado === 'rodando' || estado === 'precisa_de_voce') {
    if (podeInterromper === undefined) return { ...base, modo: 'ocupado', placeholder: 'O Claude está trabalhando…' };
    if (!podeInterromper) return { ...base, modo: 'comecando', placeholder: 'começando…' };
    if (estado === 'precisa_de_voce') {
      if (sit.espera_terminal) {
        return {
          ...base,
          modo: 'esperando',
          habilitada: true,
          botao: 'Cancelar o pedido e enviar',
          interromper: true,
          dica: 'O Claude pediu uma permissão no terminal. Para aprovar, abra o terminal. Se você escrever aqui, o pedido é cancelado e ele lê sua mensagem.',
          placeholder: 'Escreva aqui para cancelar o pedido e dizer o que fazer…',
        };
      }
      return { ...base, modo: 'esperando', habilitada: true, botao: 'Enviar', interromper: true, dica: 'O Claude está esperando uma resposta sua. Escreva aqui embaixo.' };
    }
    if (textoVazio) return { ...base, modo: 'parar', habilitada: true, botao: 'Parar', placeholder: 'Quer mudar algo? Escreva aqui.' };
    return {
      ...base,
      modo: 'interromper',
      habilitada: true,
      botao: 'Interromper e enviar',
      interromper: true,
      dica: 'O Claude está trabalhando. Se enviar agora, ele para o que está fazendo e lê sua mensagem.',
    };
  }
  // terminou | parada sem pode_responder
  return { ...base, modo: 'fechada', placeholder: 'Esta conversa não aceita resposta. Comece uma nova.' };
}

// ---------------------------------------------------------------- perguntas com opcoes
export type Perguntas = PerguntaChat['perguntas'];

/** Uma pergunta so e de uma escolha: um clique ja escolhe (poe a resposta na caixa; quem envia e a pessoa). */
export const envioDireto = (ps: Perguntas): boolean => ps.length === 1 && !ps[0].multipla;

/** Marca/desmarca a opcao `rotulo` da pergunta `i` (unica escolha troca; multipla alterna). */
export function alternarOpcao(marcadas: string[][], ps: Perguntas, i: number, rotulo: string): string[][] {
  const novo = ps.map((_, k) => [...(marcadas[k] ?? [])]);
  const atual = novo[i];
  if (!atual) return novo;
  if (ps[i].multipla) novo[i] = atual.includes(rotulo) ? atual.filter((r) => r !== rotulo) : [...atual, rotulo];
  else novo[i] = atual[0] === rotulo ? [] : [rotulo];
  return novo;
}

/** Texto simples, uma linha por pergunta respondida: "<cabecalho ou pergunta>: <rotulos, separados por virgula>". */
export function textoDasRespostas(ps: Perguntas, marcadas: string[][]): string {
  const linhas: string[] = [];
  ps.forEach((p, i) => {
    const escolhidas = p.opcoes.map((o) => o.rotulo).filter((r) => (marcadas[i] ?? []).includes(r));
    if (escolhidas.length === 0) return;
    const nome = (p.cabecalho || p.pergunta).trim();
    linhas.push(nome ? `${nome}: ${escolhidas.join(', ')}` : escolhidas.join(', '));
  });
  return linhas.join('\n');
}
