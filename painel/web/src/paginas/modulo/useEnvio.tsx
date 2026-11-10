// Envio de uma acao do modulo para um bloco: um de cada vez, com aviso de sucesso e de erro.
import { useRef, useState } from 'react';
import { useAcaoModulo } from '../../api/ganchos';
import { mensagemDoErro } from './interativos';

export function useEnvio(moduloId: string | undefined) {
  const m = useAcaoModulo(moduloId ?? '');
  const [ok, setOk] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const emVoo = useRef(false); // trava na hora: dois cliques seguidos enviam uma vez so

  async function enviar(acao: string, dados: Record<string, unknown>): Promise<boolean> {
    if (emVoo.current) return false;
    emVoo.current = true;
    setOk(false);
    setErro(null);
    try {
      await m.mutateAsync({ acao, dados });
      setOk(true);
      return true;
    } catch (e) {
      setErro(mensagemDoErro(e));
      return false;
    } finally {
      emVoo.current = false;
    }
  }
  return { enviar, enviando: m.isPending, ok, erro };
}

export function AvisoEnvio({ ok, erro }: { ok: boolean; erro: string | null }) {
  if (erro) return <p role="alert" className="text-sm text-[var(--color-error)] break-words">{erro}</p>;
  if (ok) return <p role="status" className="text-sm text-[var(--color-success)]">Feito.</p>;
  return null;
}
