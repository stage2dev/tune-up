// Bloco "formulario": campos declarados pelo modulo + um botao que chama uma acao do modulo.
import { useId, useRef, useState, type ChangeEvent } from 'react';
import { useNavigate } from 'react-router';
import { useAcoes, useIniciarExecucao } from '../../api/ganchos';
import type { Acao } from '../../api/tipos';
import { Botao, Cartao, Dialogo, Erro, Esqueleto, useAvisos } from '../../componentes';
import { caminhoDaExecucao, dispararAcao, ROTULO_RISCO, TEXTO_RISCO } from './acoes';
import { camposFaltando, dadosDoFormulario, lerCampos, semSegredos, textoDeConfirmacao, textoOuNada, valorDoCampo, type BlocoCru, type CampoLido } from './interativos';
import { AvisoEnvio, useEnvio } from './useEnvio';

export const CLASSE_CAMPO =
  'w-full min-w-0 rounded-lg border border-[var(--color-input-border)] bg-[var(--color-input-bg)] px-3 py-2 text-sm text-[var(--color-text)]';

function Entrada({ c, idBase, valor, invalido, aoMudar, aoSair }: { c: CampoLido; idBase: string; valor: string; invalido: boolean; aoMudar: (v: string) => void; aoSair?: () => void }) {
  const id = `${idBase}-${c.id}`;
  const secreto = c.tipo === 'segredo'; // nao controlado: o valor nao vai para o estado do React nem para o atributo value
  const comum = { id, className: CLASSE_CAMPO, ...(secreto ? { name: c.id } : { value: valor }), 'aria-invalid': invalido || undefined, required: c.obrigatorio, onBlur: aoSair };
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

/** Formulario de um bloco. Com `catalogo` dispara uma acao do catalogo (campo.id = nome do parametro); senao um comando do modulo (`acao`). */
export function Formulario({ b, moduloId }: { b: BlocoCru; moduloId?: string }) {
  const catalogo = textoOuNada(b.catalogo);
  return catalogo ? <FormularioCatalogo b={b} moduloId={moduloId} id={catalogo} /> : <FormularioBase b={b} moduloId={moduloId} acaoCat={null} disparar={null} />;
}

function FormularioCatalogo({ b, moduloId, id }: { b: BlocoCru; moduloId?: string; id: string }) {
  const acoes = useAcoes();
  const iniciar = useIniciarExecucao();
  const navegar = useNavigate();
  const { avisar } = useAvisos();
  if (acoes.isPending) return <Cartao titulo={textoOuNada(b.titulo)}><Esqueleto className="h-24 w-full" /></Cartao>;
  if (acoes.isError) return <Cartao titulo={textoOuNada(b.titulo)}><Erro erro={acoes.error} aoTentar={() => void acoes.refetch()} /></Cartao>;
  const acaoCat = acoes.data.find((a) => a.id === id);
  if (!acaoCat) return <Cartao titulo={textoOuNada(b.titulo)}><p role="note" className="text-sm text-[var(--color-text-secondary)]">A ação “{id}” não existe neste projeto.</p></Cartao>;
  async function disparar(valores: Record<string, string>) {
    const r = await dispararAcao((corpo) => iniciar.mutateAsync(corpo), acaoCat as Acao, valores);
    if (r.tipo === 'ok') {
      avisar({ tipo: 'sucesso', titulo: 'Começou', texto: `${(acaoCat as Acao).titulo}: o Claude está trabalhando em segundo plano.` });
      void navegar(caminhoDaExecucao(r.execucao.id));
    } else if (r.tipo === 'ja_rodando') {
      avisar({ tipo: 'info', titulo: 'Já está rodando', texto: r.mensagem });
      if (r.execucaoId) void navegar(caminhoDaExecucao(r.execucaoId));
    } else {
      avisar({ tipo: 'erro', titulo: 'Não deu para começar', texto: r.mensagem });
    }
  }
  return <FormularioBase b={b} moduloId={moduloId} acaoCat={acaoCat} disparar={disparar} />;
}

type Disparar = (valores: Record<string, string>) => Promise<void>;

function FormularioBase({ b, moduloId, acaoCat, disparar }: { b: BlocoCru; moduloId?: string; acaoCat: Acao | null; disparar: Disparar | null }) {
  const campos = lerCampos(b.campos);
  const sec = !acaoCat && b.secundario && typeof b.secundario === 'object' ? (b.secundario as Record<string, unknown>) : null;
  const acaoSec = sec ? textoOuNada(sec.acao) : undefined; // segundo botao no mesmo cartao (Recusar ao lado de Aprovar)
  const [usarSec, setUsarSec] = useState(false);
  const acao = acaoCat ? acaoCat.id : usarSec ? acaoSec : textoOuNada(b.acao);
  const [editados, setEditados] = useState<Record<string, string>>({}); // so o que a pessoa mexeu: a releitura de 15 s nao apaga
  const [invalidos, setInvalidos] = useState<string[]>([]); // campos que faltavam no ultimo envio
  const [pedindo, setPedindo] = useState<Record<string, string> | null>(null); // valores lidos, esperando o "sim" do dialogo
  const [disparando, setDisparando] = useState(false);
  const emVoo = useRef(false);
  const formRef = useRef<HTMLFormElement>(null);
  const { enviar, enviando: enviandoModulo, ok, erro } = useEnvio(moduloId);
  const enviando = enviandoModulo || disparando;
  const textoConfirmar = textoDeConfirmacao(acaoCat, usarSec ? sec?.confirmar : b.confirmar);
  const faltando = camposFaltando(campos, editados); // segredo nunca esta em `editados`: so e checado no envio
  const idBase = `form-${moduloId ?? 'm'}-${useId()}`; // dois formularios na mesma aba (post e video): ids e rotulos nao se cruzam
  const aoSair = !acaoCat && b.salvar_ao_sair === true; // salva ao sair do campo (e no Enter): sem botao, nada digitado fica so na tela

  async function executar(lidos: Record<string, string>, secundario = usarSec) {
    const qual = acaoCat ? acaoCat.id : secundario ? acaoSec : textoOuNada(b.acao);
    if (!qual || emVoo.current) return;
    if (disparar) {
      emVoo.current = true;
      setDisparando(true);
      try {
        await disparar(Object.fromEntries(campos.map((c) => [c.id, valorDoCampo(c, lidos)])));
      } finally {
        emVoo.current = false;
        setDisparando(false);
        setPedindo(null);
      }
      return;
    }
    const feito = await enviar(qual, dadosDoFormulario(b.dados_fixos, campos, lidos));
    setPedindo(null);
    if (feito) {
      setEditados((v) => semSegredos(campos, v));
      for (const c of campos) if (c.tipo === 'segredo') { const el = formRef.current?.elements.namedItem(c.id); if (el instanceof HTMLInputElement) el.value = ''; }
      setInvalidos([]);
    }
  }

  async function aoEnviar(e: { preventDefault: () => void }, secundario = false) {
    e.preventDefault();
    const form = formRef.current;
    if (enviando || !form || !(secundario ? acaoSec : acaoCat ? acaoCat.id : textoOuNada(b.acao))) return;
    setUsarSec(secundario);
    const lidos = { ...editados }; // segredos lidos do DOM so agora
    for (const c of campos) if (c.tipo === 'segredo') lidos[c.id] = String(new FormData(form).get(c.id) ?? '');
    const falta = camposFaltando(campos, lidos);
    setInvalidos(falta);
    if (falta.length > 0) return;
    const confirmar = textoDeConfirmacao(acaoCat, secundario ? sec?.confirmar : b.confirmar);
    if (confirmar) setPedindo(lidos);
    else await executar(lidos, secundario);
  }

  return (
    <Cartao titulo={textoOuNada(b.titulo)}>
      <form ref={formRef} onSubmit={(e) => void aoEnviar(e)} className="grid gap-3" autoComplete="off" noValidate>
        {textoOuNada(b.descricao) && <p className="text-sm text-[var(--color-text-secondary)] break-words whitespace-pre-line">{textoOuNada(b.descricao)}</p>}
        {!acao && <p role="note" className="text-xs text-[var(--color-text-tertiary)]">Este formulário não diz qual ação chamar.</p>}
        {campos.map((c) => (
          <Entrada key={c.id} c={c} idBase={idBase} valor={valorDoCampo(c, editados)} invalido={invalidos.includes(c.id) && (c.tipo === 'segredo' || faltando.includes(c.id))} aoMudar={(v) => setEditados((x) => ({ ...x, [c.id]: v }))}
            aoSair={aoSair && c.tipo !== 'segredo' ? () => { if (c.id in editados && editados[c.id] !== c.valor) void aoEnviar({ preventDefault: () => undefined }); } : undefined} />
        ))}
        <div className="flex flex-wrap items-center gap-3">
          {aoSair ? enviando && <span role="status" className="text-sm text-[var(--color-text-secondary)]">Salvando…</span> : (
            <Botao type="submit" variante={b.discreto === true ? 'secundario' : 'primario'} enviando={enviando && pedindo === null && !usarSec} textoEnviando={acaoCat ? 'Começando…' : 'Enviando…'} disabled={!acaoCat && !textoOuNada(b.acao)}>{textoOuNada(b.botao) ?? 'Enviar'}</Botao>
          )}
          {acaoSec && (
            <Botao variante="secundario" enviando={enviando && pedindo === null && usarSec} disabled={enviando}
              onClick={(e) => void aoEnviar(e, true)}>{textoOuNada(sec?.botao) ?? 'Recusar'}</Botao>
          )}
          <AvisoEnvio ok={ok} erro={erro} />
        </div>
      </form>
      <Dialogo aberto={pedindo !== null} titulo={acaoCat?.titulo ?? textoOuNada(b.titulo) ?? 'Confirmar'} textoConfirmar={acaoCat ? 'Começar' : 'Confirmar'} enviando={enviando}
        aoConfirmar={() => pedindo && void executar(pedindo)} aoFechar={() => setPedindo(null)}>
        <p className="break-words">{textoConfirmar}</p>
        {acaoCat && <p className="text-xs"><strong>{ROTULO_RISCO[acaoCat.risco]}.</strong> {TEXTO_RISCO[acaoCat.risco]}</p>}
      </Dialogo>
    </Cartao>
  );
}
