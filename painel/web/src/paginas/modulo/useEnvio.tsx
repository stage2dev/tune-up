// Envio de uma acao do modulo para um bloco: um de cada vez, com aviso de sucesso e de erro.
import { useRef, useState } from 'react';
import { useAcaoModulo } from '../../api/ganchos';
import { mensagemDoErro } from './interativos';

export function useEnvio(moduloId: string | undefined) {
  const m = useAcaoModulo(moduloId ?? '');
  const [ok, setOk] = useState<string | false>(false); // texto que o modulo devolveu (ou "Feito.")
  const [erro, setErro] = useState<string | null>(null);
  const emVoo = useRef(false); // trava na hora: dois cliques seguidos enviam uma vez so

  async function enviar(acao: string, dados: Record<string, unknown>): Promise<boolean> {
    if (emVoo.current) return false;
    emVoo.current = true;
    setOk(false);
    setErro(null);
    try {
      const r = await m.mutateAsync({ acao, dados });
      const msg = r?.resultado?.mensagem;
      setOk(typeof msg === 'string' && msg.trim() ? msg.slice(0, 300) : 'Feito.');
      return true;
    } catch (e) {
      setErro(mensagemDoErro(e));
      return false;
    } finally {
      emVoo.current = false;
      m.reset(); // nao deixa os dados enviados (ex.: segredo) no cache da mutacao
    }
  }
  return { enviar, enviando: m.isPending, ok, erro };
}

export function AvisoEnvio({ ok, erro }: { ok: string | false; erro: string | null }) {
  if (erro) return <p role="alert" className="text-sm text-[var(--color-error)] break-words">{erro}</p>;
  if (ok) return <p role="status" className="text-sm text-[var(--color-success)] break-words">{ok}</p>;
  return null;
}
