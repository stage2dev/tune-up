// Skills escolhidas para o proximo pedido (ids). Fica em TelaChat; trocar de conversa zera.
import { useCallback, useState } from 'react';
import { alternar, incluir, MAX_HABILIDADES, podarInexistentes, tirarEnviados } from './habilidades';
import type { Habilidade } from '../../api/tipos';

export interface SkillsDoPedido {
  ids: string[];
  aviso: string | null;
  /** Clique da lista: poe ou tira. */
  alternar: (id: string) => void;
  /** Soltar na caixa: so poe. */
  por: (id: string) => void;
  remover: (id: string) => void;
  /** Depois do envio: tira so os ids que foram enviados. */
  removerEnviados: (enviados: string[]) => void;
  /** Lista nova do servidor: tira as que nao existem mais. */
  podar: (habs: Habilidade[]) => void;
  limpar: () => void;
}

const AVISO = `No máximo ${MAX_HABILIDADES} skills por pedido.`;

export function useSkillsDoPedido(): SkillsDoPedido {
  const [ids, setIds] = useState<string[]>([]);
  const [aviso, setAviso] = useState<string | null>(null);
  const alt = useCallback(
    (id: string) => {
      const r = alternar(ids, id);
      setAviso(r.cheio ? AVISO : null);
      if (!r.cheio) setIds(r.ids);
    },
    [ids],
  );
  const por = useCallback(
    (id: string) => {
      const r = incluir(ids, id);
      setAviso(r.cheio ? AVISO : null);
      if (!r.cheio) setIds(r.ids);
    },
    [ids],
  );
  const remover = useCallback((id: string) => {
    setAviso(null);
    setIds((l) => l.filter((x) => x !== id));
  }, []);
  const removerEnviados = useCallback((enviados: string[]) => {
    setAviso(null);
    setIds((l) => tirarEnviados(l, enviados));
  }, []);
  const podar = useCallback((habs: Habilidade[]) => setIds((l) => podarInexistentes(l, habs)), []);
  const limpar = useCallback(() => {
    setAviso(null);
    setIds([]);
  }, []);
  return { ids, aviso, alternar: alt, por, remover, removerEnviados, podar, limpar };
}
