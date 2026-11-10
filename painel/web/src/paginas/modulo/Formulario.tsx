// Bloco "formulario": campos declarados pelo modulo + um botao que chama uma acao do modulo.
import { useState, type ChangeEvent, type FormEvent } from 'react';
import type { Bloco } from '../../api/tipos';
import { Botao, Cartao } from '../../componentes';
import { camposFaltando, dadosDoFormulario, lerCampos, semSegredos, textoOuNada, valorDoCampo, type CampoLido } from './interativos';
import { AvisoEnvio, useEnvio } from './useEnvio';

export const CLASSE_CAMPO =
  'w-full min-w-0 rounded-lg border border-[var(--color-input-border)] bg-[var(--color-input-bg)] px-3 py-2 text-sm text-[var(--color-text)]';

function Entrada({ c, idBase, valor, invalido, aoMudar }: { c: CampoLido; idBase: string; valor: string; invalido: boolean; aoMudar: (v: string) => void }) {
  const id = `${idBase}-${c.id}`;
  const secreto = c.tipo === 'segredo'; // nao controlado: o valor nao vai para o estado do React nem para o atributo value
  const comum = { id, className: CLASSE_CAMPO, ...(secreto ? { name: c.id } : { value: valor }), 'aria-invalid': invalido || undefined, required: c.obrigatorio };
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
        <input {...comum} type={secreto ? 'password' : 'text'} autoComplete="off" {...(secreto ? {} : { onChange: (e: ChangeEvent<HTMLInputElement>) => aoMudar(e.target.value) })} />
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
  const [invalidos, setInvalidos] = useState<string[]>([]); // campos que faltavam no ultimo envio
  const { enviar, enviando, ok, erro } = useEnvio(moduloId);
  const faltando = camposFaltando(campos, editados); // segredo nunca esta em `editados`: so e checado no envio
  const idBase = `form-${moduloId ?? 'm'}`;

  async function aoEnviar(e: FormEvent) {
    e.preventDefault();
    if (enviando || !acao) return;
    const form = e.currentTarget as HTMLFormElement;
    const lidos = { ...editados }; // segredos lidos do DOM so agora
    for (const c of campos) if (c.tipo === 'segredo') lidos[c.id] = String(new FormData(form).get(c.id) ?? '');
    const falta = camposFaltando(campos, lidos);
    setInvalidos(falta);
    if (falta.length > 0) return;
    if (await enviar(acao, dadosDoFormulario(b.dados_fixos, campos, lidos))) {
      setEditados((v) => semSegredos(campos, v));
      for (const c of campos) if (c.tipo === 'segredo') { const el = form.elements.namedItem(c.id); if (el instanceof HTMLInputElement) el.value = ''; }
      setInvalidos([]);
    }
  }

  return (
    <Cartao titulo={textoOuNada(b.titulo)}>
      <form onSubmit={(e) => void aoEnviar(e)} className="grid gap-3" autoComplete="off" noValidate>
        {textoOuNada(b.descricao) && <p className="text-sm text-[var(--color-text-secondary)] break-words whitespace-pre-line">{textoOuNada(b.descricao)}</p>}
        {!acao && <p role="note" className="text-xs text-[var(--color-text-tertiary)]">Este formulário não diz qual ação chamar.</p>}
        {campos.map((c) => (
          <Entrada key={c.id} c={c} idBase={idBase} valor={valorDoCampo(c, editados)} invalido={invalidos.includes(c.id) && (c.tipo === 'segredo' || faltando.includes(c.id))} aoMudar={(v) => setEditados((x) => ({ ...x, [c.id]: v }))} />
        ))}
        <div className="flex flex-wrap items-center gap-3">
          <Botao type="submit" enviando={enviando} textoEnviando="Enviando…" disabled={!acao}>{textoOuNada(b.botao) ?? 'Enviar'}</Botao>
          <AvisoEnvio ok={ok} erro={erro} />
        </div>
      </form>
    </Cartao>
  );
}
