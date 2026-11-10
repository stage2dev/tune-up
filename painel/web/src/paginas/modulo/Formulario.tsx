// Bloco "formulario": campos declarados pelo modulo + um botao que chama uma acao do modulo.
import { useState, type FormEvent } from 'react';
import type { Bloco } from '../../api/tipos';
import { Botao, Cartao } from '../../componentes';
import { camposFaltando, dadosDoFormulario, lerCampos, semSegredos, textoOuNada, valorDoCampo, type CampoLido } from './interativos';
import { AvisoEnvio, useEnvio } from './useEnvio';

export const CLASSE_CAMPO =
  'w-full min-w-0 rounded-lg border border-[var(--color-input-border)] bg-[var(--color-input-bg)] px-3 py-2 text-sm text-[var(--color-text)]';

function Entrada({ c, idBase, valor, invalido, aoMudar }: { c: CampoLido; idBase: string; valor: string; invalido: boolean; aoMudar: (v: string) => void }) {
  const id = `${idBase}-${c.id}`;
  const comum = { id, className: CLASSE_CAMPO, value: valor, 'aria-invalid': invalido || undefined, required: c.obrigatorio };
  return (
    <div className="grid gap-1">
      <label htmlFor={id} className="text-sm font-medium text-[var(--color-text)]">
        {c.rotulo}
        {!c.obrigatorio && <span className="font-normal text-[var(--color-text-tertiary)]"> (opcional)</span>}
      </label>
      {c.tipo === 'escolha' ? (
        <select {...comum} onChange={(e) => aoMudar(e.target.value)}>
          <option value="">Escolha…</option>
          {c.opcoes.map((o) => <option key={o.valor} value={o.valor}>{o.rotulo}</option>)}
        </select>
      ) : c.tipo === 'texto_longo' ? (
        <textarea {...comum} rows={4} className={`${CLASSE_CAMPO} break-words`} autoComplete="off" onChange={(e) => aoMudar(e.target.value)} />
      ) : (
        <input {...comum} type={c.tipo === 'segredo' ? 'password' : 'text'} autoComplete="off" onChange={(e) => aoMudar(e.target.value)} />
      )}
      {c.ajuda && <span className="text-xs text-[var(--color-text-tertiary)] break-words">{c.ajuda}</span>}
      {invalido && <span role="alert" className="text-xs text-[var(--color-error)]">Preencha este campo.</span>}
    </div>
  );
}

export function Formulario({ b, moduloId }: { b: Bloco; moduloId?: string }) {
  const campos = lerCampos(b.campos);
  const acao = textoOuNada(b.acao);
  const [editados, setEditados] = useState<Record<string, string>>({}); // so o que a pessoa mexeu: a releitura de 15 s nao apaga
  const [tentou, setTentou] = useState(false);
  const { enviar, enviando, ok, erro } = useEnvio(moduloId);
  const faltando = camposFaltando(campos, editados);
  const idBase = `form-${moduloId ?? 'm'}`;

  async function aoEnviar(e: FormEvent) {
    e.preventDefault();
    if (enviando || !acao) return;
    setTentou(true);
    if (faltando.length > 0) return;
    if (await enviar(acao, dadosDoFormulario(b.dados_fixos, campos, editados))) {
      setEditados((v) => semSegredos(campos, v));
      setTentou(false);
    }
  }

  return (
    <Cartao titulo={textoOuNada(b.titulo)}>
      <form onSubmit={(e) => void aoEnviar(e)} className="grid gap-3" autoComplete="off" noValidate>
        {textoOuNada(b.descricao) && <p className="text-sm text-[var(--color-text-secondary)] break-words whitespace-pre-line">{textoOuNada(b.descricao)}</p>}
        {!acao && <p role="note" className="text-xs text-[var(--color-text-tertiary)]">Este formulário não diz qual ação chamar.</p>}
        {campos.map((c) => (
          <Entrada key={c.id} c={c} idBase={idBase} valor={valorDoCampo(c, editados)} invalido={tentou && faltando.includes(c.id)} aoMudar={(v) => setEditados((x) => ({ ...x, [c.id]: v }))} />
        ))}
        <div className="flex flex-wrap items-center gap-3">
          <Botao type="submit" enviando={enviando} textoEnviando="Enviando…" disabled={!acao}>{textoOuNada(b.botao) ?? 'Enviar'}</Botao>
          <AvisoEnvio ok={ok} erro={erro} />
        </div>
      </form>
    </Cartao>
  );
}
