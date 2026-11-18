// Decisoes da secao Plugins (puras, sem React).
import { ErroApi } from '../../api/cliente';
import type { Plugin, RespMudarPlugin } from '../../api/tipos';
import { textoFalha } from './logica';

export const TIPO_ARRASTE = 'application/x-tuneup-plugin';
export const TEXTO_SUCESSO = 'Vale na próxima sessão';
export const TEXTO_CONFLITO = 'Os ajustes mudaram por fora; recarreguei a lista';
export const TEXTO_FIXO = 'O tune-up não se desliga por aqui: é ele que roda este painel.';
export const TEXTO_VAZIO = 'Nenhum plugin nos seus ajustes do Claude';

const ORIGEM = { usuario: 'seus ajustes do Claude', projeto: 'os ajustes do projeto', local: 'os ajustes locais do projeto' } as const;

/** Divide a lista nas duas colunas, mantendo a ordem do servidor. */
export function dividirColunas(lista: Plugin[]): { ligados: Plugin[]; desligados: Plugin[] } {
  return { ligados: lista.filter((p) => p.ligado), desligados: lista.filter((p) => !p.ligado) };
}

export function pesoEstimado(p: Plugin): string {
  if (p.skills === 0 && p.agentes === 0 && p.peso === 0) return 'Peso: não sei medir (pasta de instalação desconhecida)';
  return `${p.skills} skill${p.skills === 1 ? '' : 's'}, ${p.agentes} agente${p.agentes === 1 ? '' : 's'}, ~${p.peso} caracteres de descrição`;
}

export function origemDoValor(p: Plugin): string {
  return `Valor vindo de ${ORIGEM[p.origem]}`;
}

/** Aviso quando o projeto ou o local troca o valor do usuario; null caso contrario. */
export function avisoSobreposto(p: Plugin): string | null {
  return p.sobreposto ? 'O projeto sobrepõe: mudar aqui não muda o que vale neste projeto.' : null;
}

export function botaoDoPlugin(p: Plugin): { texto: string; textoEnviando: string; pedir: boolean; variante: 'primario' | 'secundario' } {
  return p.ligado
    ? { texto: 'Desligar', textoEnviando: 'Desligando…', pedir: false, variante: 'secundario' }
    : { texto: 'Ligar', textoEnviando: 'Ligando…', pedir: true, variante: 'primario' };
}

export type Resultado = 'ok' | 'conflito' | 'erro' | 'ignorado';

export interface DepsMovedor {
  enviar: (id: string, enabled: boolean) => Promise<RespMudarPlugin>;
  /** Id que esta sendo enviado (ou null): a tela desabilita os cartoes. */
  aoOcupar: (id: string | null) => void;
  aoSucesso: (r: RespMudarPlugin) => void;
  aoConflito: (mensagem: string) => void;
  aoErro: (mensagem: string) => void;
}

/** Um envio por vez: clique ou arraste durante um envio em andamento e ignorado. */
export function criarMovedor(d: DepsMovedor) {
  let ocupado = false;
  return async function mover(id: string, ligar: boolean): Promise<Resultado> {
    if (ocupado) return 'ignorado';
    ocupado = true;
    d.aoOcupar(id);
    try {
      d.aoSucesso(await d.enviar(id, ligar));
      return 'ok';
    } catch (erro) {
      if (erro instanceof ErroApi && erro.status === 409) {
        d.aoConflito(textoFalha(erro));
        return 'conflito';
      }
      d.aoErro(textoFalha(erro));
      return 'erro';
    } finally {
      ocupado = false;
      d.aoOcupar(null);
    }
  };
}
