// Dialogo de uma acao que pede texto (Planejar fase, Investigar), montado a partir dos params da API.
import { useState } from 'react';
import { Dialogo } from '../../componentes';
import { AvisoProblema } from './AvisoProblema';
import { useRodar } from './useRodar';
import type { Acao } from '../../api/tipos';

interface Props {
  acao: Acao;
  aberto: boolean;
  aoFechar: () => void;
  explicacao: string;
}

export function DialogoTexto({ acao, aberto, aoFechar, explicacao }: Props) {
  const [valores, setValores] = useState<Record<string, string>>({});
  const [faltou, setFaltou] = useState(false);
  const { rodar, enviando, problema, limpar } = useRodar(() => {
    setValores({});
    aoFechar();
  });

  const fechar = () => {
    limpar();
    setFaltou(false);
    aoFechar();
  };
  const confirmar = () => {
    const params: Record<string, string> = {};
    for (const p of acao.params) {
      const v = (valores[p.nome] ?? '').trim();
      if (p.obrigatorio && !v) {
        setFaltou(true);
        return;
      }
      if (v) params[p.nome] = v;
    }
    setFaltou(false);
    rodar({ acao: acao.id, params });
  };

  return (
    <Dialogo aberto={aberto} titulo={acao.titulo} textoConfirmar="Começar" enviando={enviando} aoFechar={fechar} aoConfirmar={confirmar}>
      <p>{explicacao}</p>
      {acao.params.map((p) => {
        const id = `campo-${acao.id}-${p.nome}`;
        return (
          <div key={p.nome} className="grid grid-cols-1 gap-1">
            <label htmlFor={id} className="text-[var(--color-text)] font-medium">
              {p.rotulo}
            </label>
            {p.tipo === 'escolha' ? (
              <select
                id={id}
                value={valores[p.nome] ?? ''}
                onChange={(e) => setValores({ ...valores, [p.nome]: e.target.value })}
                className="h-9 rounded-lg border border-[var(--color-input-border)] bg-[var(--color-input-bg)] px-2 text-[var(--color-text)]"
              >
                <option value="">Escolha…</option>
                {(p.opcoes ?? []).map((o) => (
                  <option key={o}>{o}</option>
                ))}
              </select>
            ) : (
              <textarea
                id={id}
                rows={4}
                maxLength={p.max ?? 500}
                value={valores[p.nome] ?? ''}
                onChange={(e) => setValores({ ...valores, [p.nome]: e.target.value })}
                className="w-full rounded-lg border border-[var(--color-input-border)] bg-[var(--color-input-bg)] p-2 text-[var(--color-text)]"
              />
            )}
            {p.ajuda && <p className="text-xs">{p.ajuda}</p>}
          </div>
        );
      })}
      {faltou && (
        <p role="alert" className="text-[var(--color-error)]">
          Preencha o campo para continuar.
        </p>
      )}
      <AvisoProblema problema={problema} />
    </Dialogo>
  );
}
