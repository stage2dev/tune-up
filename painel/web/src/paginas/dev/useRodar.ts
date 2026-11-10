// Envia uma acao (POST /api/execucoes), guarda o erro para mostrar no dialogo e leva para a tela da execucao.
import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router';
import { chaves } from '../../api/ganchos';
import { useAvisos } from '../../componentes';
import { iniciar, traduzirErroInicio, type PedidoInicio, type ResultadoErro } from './logica';

export function useRodar(aoComecar?: () => void) {
  const qc = useQueryClient();
  const ir = useNavigate();
  const { avisar } = useAvisos();
  const [problema, setProblema] = useState<ResultadoErro | null>(null);

  const mut = useMutation({
    mutationFn: iniciar,
    onSuccess: (e) => {
      void qc.invalidateQueries({ queryKey: chaves.execucoes });
      setProblema(null);
      aoComecar?.();
      avisar({ tipo: 'sucesso', titulo: 'Começou', texto: e.titulo });
      ir(`/execucoes/${encodeURIComponent(e.id)}`);
    },
    onError: (e) => setProblema(traduzirErroInicio(e)),
  });

  return {
    rodar: (p: PedidoInicio) => {
      setProblema(null);
      mut.mutate(p);
    },
    enviando: mut.isPending,
    problema,
    limpar: () => setProblema(null),
  };
}
