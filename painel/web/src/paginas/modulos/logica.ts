// Decisoes da tela Modulos (puras, sem React).
import { ErroApi } from '../../api/cliente';
import type { Embutido } from '../../api/tipos';

export interface BotaoEmbutido {
  texto: string;
  variante: 'primario' | 'secundario';
  /** Estado que o clique pede ao servidor. */
  pedir: boolean;
}

export function rotuloEstado(e: Embutido): string {
  return e.ligado ? 'Ligado' : 'Desligado';
}

export function botaoDoEmbutido(e: Embutido): BotaoEmbutido {
  return e.ligado ? { texto: 'Desligar', variante: 'secundario', pedir: false } : { texto: 'Ligar', variante: 'primario', pedir: true };
}

/** Texto do botao enquanto o pedido esta em andamento (pedir = o estado pedido). */
export function textoEnviando(pedir: boolean): string {
  return pedir ? 'Ligando…' : 'Desligando…';
}

/** Desligar sempre pode; ligar so se a maquina permite. */
export function motivoBloqueio(e: Embutido): string | null {
  if (e.ligado || e.disponivel) return null;
  return `Não dá para ligar neste computador: ${e.motivo ?? 'não é possível aqui.'}`;
}

export function textoSucesso(titulo: string, ligou: boolean): string {
  return ligou ? `${titulo} ligado — já está no menu` : `${titulo} desligado — saiu do menu`;
}

export function tituloFalha(ligou: boolean): string {
  return ligou ? 'Não deu para ligar' : 'Não deu para desligar';
}

/** Mensagem simples para a falha: texto do servidor, ou o aviso de painel fora do ar. */
export function textoFalha(erro: unknown): string {
  if (erro instanceof ErroApi && erro.message) return erro.message;
  if (erro instanceof Error && erro.message) return erro.message;
  return 'Algo deu errado. Tente de novo.';
}
