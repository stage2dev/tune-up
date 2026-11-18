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

/** Plugin que nao esta nos ajustes do usuario: o POST so mexe la, entao sem botao e sem arrastar. */
export function soForaDoUsuario(p: Plugin): string | null {
  return p.valores.usuario === undefined ? `Esse valor vive só n${ORIGEM[p.origem]}: mude por lá.` : null;
}

/** O POST so troca o valor do settings do usuario: e ele que o botao inverte (no sobreposto difere do que vale). */
export function valorDoUsuario(p: Plugin): boolean {
  return p.valores.usuario ?? p.ligado;
}

export function botaoDoPlugin(p: Plugin): { texto: string; textoEnviando: string; pedir: boolean; variante: 'primario' | 'secundario' } {
  const sufixo = p.sobreposto ? ' nos seus ajustes' : '';
  return valorDoUsuario(p)
    ? { texto: `Desligar${sufixo}`, textoEnviando: 'Desligando…', pedir: false, variante: 'secundario' }
    : { texto: `Ligar${sufixo}`, textoEnviando: 'Ligando…', pedir: true, variante: 'primario' };
}

/** Aviso de sucesso. Igual ao `aviso` do servidor: se o projeto/local ainda decide (sobreposto depois de gravar),
 * nao promete "vale na proxima sessao" e diz quem decide pela `origem`. */
export function avisoSucesso(r: RespMudarPlugin, id: string): { titulo: string; texto?: string } {
  const p = r.plugins.find((x) => x.id === id);
  if (!p?.sobreposto) return { titulo: TEXTO_SUCESSO };
  return { titulo: 'Salvo nos seus ajustes', texto: `Mas neste projeto quem decide ainda são ${ORIGEM[p.origem]}.` };
}

/** Arrastar = mudar de coluna; num sobreposto o cartao nao muda de coluna, entao so o botao. */
export function podeArrastar(p: Plugin): boolean {
  return !p.fixo && !p.sobreposto && p.valores.usuario !== undefined;
}

/** 409: o titulo de conflito so quando o arquivo mudou durante a gravacao; nos outros, a frase do servidor. */
export function avisoConflito(e: ErroApi): { titulo: string; texto?: string } {
  return e.codigo === 'mudou' ? { titulo: TEXTO_CONFLITO, texto: e.message } : { titulo: e.message };
}

export type Resultado = 'ok' | 'conflito' | 'erro' | 'ignorado';

export interface DepsMovedor {
  enviar: (id: string, enabled: boolean) => Promise<RespMudarPlugin>;
  /** Id que esta sendo enviado (ou null): a tela desabilita os cartoes. */
  aoOcupar: (id: string | null) => void;
  aoSucesso: (r: RespMudarPlugin, id: string) => void;
  aoConflito: (erro: ErroApi) => void;
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
      const r = await d.enviar(id, ligar);
      if (r.plugins.find((p) => p.id === id)?.valores.usuario !== ligar) {
        d.aoErro('O servidor respondeu, mas seu ajuste não mudou.');
        return 'erro';
      }
      d.aoSucesso(r, id);
      return 'ok';
    } catch (erro) {
      if (erro instanceof ErroApi && erro.status === 409) {
        d.aoConflito(erro);
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
