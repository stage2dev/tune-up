// Botao que roda uma acao numa sessao do Claude Code em segundo plano.
// Com parametros ou pedido de confirmacao abre um dialogo; depois de disparar leva para /execucoes/<id>.
import { useState, type ReactNode } from 'react';
import { useNavigate } from 'react-router';
import { Play } from 'lucide-react';
import { useAcoes, useIniciarExecucao } from '../../api/ganchos';
import type { Acao, ParamAcao } from '../../api/tipos';
import { Botao, Dialogo, Erro, Esqueleto, Selo, useAvisos } from '../../componentes';
import { acoesDoGrupo, caminhoDaExecucao, dispararAcao, precisaDeDialogo, ROTULO_RISCO, TEXTO_RISCO, validarParams, valoresIniciais } from './acoes';

const CAMPO =
  'w-full min-w-0 rounded-lg border border-[var(--color-input-border)] bg-[var(--color-input-bg)] px-3 py-2 text-sm text-[var(--color-text)]';

function Campo({ p, valor, erro, aoMudar, aoEnter }: { p: ParamAcao; valor: string; erro?: string; aoMudar: (v: string) => void; aoEnter: () => void }) {
  const id = `param-${p.nome}`;
  return (
    <div className="grid gap-1">
      <label htmlFor={id} className="text-sm font-medium text-[var(--color-text)]">
        {p.rotulo}
        {!p.obrigatorio && <span className="font-normal text-[var(--color-text-tertiary)]"> (opcional)</span>}
      </label>
      {p.tipo === 'escolha' ? (
        <select id={id} className={CAMPO} value={valor} onChange={(e) => aoMudar(e.target.value)} aria-invalid={!!erro}>
          <option value="">Escolha…</option>
          {(p.opcoes ?? []).map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </select>
      ) : (
        <input
          id={id}
          className={CAMPO}
          value={valor}
          maxLength={p.max ?? 500}
          onChange={(e) => aoMudar(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              aoEnter();
            }
          }}
          aria-invalid={!!erro}
          autoComplete="off"
        />
      )}
      {p.ajuda && <span className="text-xs text-[var(--color-text-tertiary)]">{p.ajuda}</span>}
      {erro && (
        <span role="alert" className="text-xs text-[var(--color-error)]">
          {erro}
        </span>
      )}
    </div>
  );
}

export function BotaoAcao({ acao, variante = 'secundario', children }: { acao: Acao; variante?: 'primario' | 'secundario'; children?: ReactNode }) {
  const iniciar = useIniciarExecucao();
  const navegar = useNavigate();
  const { avisar } = useAvisos();
  const [aberto, setAberto] = useState(false);
  const [valores, setValores] = useState<Record<string, string>>({});
  const [erros, setErros] = useState<Record<string, string>>({});
  const [enviando, setEnviando] = useState(false);

  const rodar = async () => {
    const e = validarParams(acao.params, valores);
    setErros(e);
    if (Object.keys(e).length > 0) return;
    setEnviando(true);
    const r = await dispararAcao((corpo) => iniciar.mutateAsync(corpo), acao, valores);
    setEnviando(false);
    if (r.tipo === 'ok') {
      setAberto(false);
      avisar({ tipo: 'sucesso', titulo: 'Começou', texto: `${acao.titulo}: o Claude está trabalhando em segundo plano.` });
      void navegar(caminhoDaExecucao(r.execucao.id));
    } else if (r.tipo === 'ja_rodando') {
      setAberto(false);
      avisar({ tipo: 'info', titulo: 'Já está rodando', texto: r.mensagem });
      if (r.execucaoId) void navegar(caminhoDaExecucao(r.execucaoId));
    } else {
      avisar({ tipo: 'erro', titulo: 'Não deu para começar', texto: r.mensagem });
    }
  };

  const clicar = () => {
    if (!precisaDeDialogo(acao)) {
      void rodar();
      return;
    }
    setValores(valoresIniciais(acao.params));
    setErros({});
    setAberto(true);
  };

  return (
    <>
      <Botao variante={variante} icone={<Play size={14} aria-hidden="true" />} enviando={enviando && !aberto} textoEnviando="Começando…" onClick={clicar}>
        {children ?? 'Rodar'}
      </Botao>
      <Dialogo aberto={aberto} titulo={acao.titulo} textoConfirmar="Começar" enviando={enviando} aoConfirmar={() => void rodar()} aoFechar={() => setAberto(false)}>
        <p>{acao.descricao}</p>
        <p className="text-xs">
          <strong>{ROTULO_RISCO[acao.risco]}.</strong> {TEXTO_RISCO[acao.risco]}
        </p>
        {acao.params.map((p) => (
          <Campo
            key={p.nome}
            p={p}
            valor={valores[p.nome] ?? ''}
            erro={erros[p.nome]}
            aoMudar={(v) => setValores((a) => ({ ...a, [p.nome]: v }))}
            aoEnter={() => void rodar()}
          />
        ))}
        {acao.confirmar && <p className="text-xs">Quer mesmo começar? Você poderá parar a qualquer momento na tela da execução.</p>}
      </Dialogo>
    </>
  );
}

/** Botoes das acoes de um grupo. Enquanto a lista carrega mostra esqueleto; sem acoes, `vazio`. */
export function BotoesDoGrupo({ grupo, vazio }: { grupo: string; vazio?: ReactNode }) {
  const acoes = useAcoes();
  if (acoes.isPending) return <Esqueleto className="h-9 w-40" />;
  if (acoes.isError) return <Erro erro={acoes.error} aoTentar={() => void acoes.refetch()} />;
  const lista = acoesDoGrupo(acoes.data, grupo);
  if (lista.length === 0) return <>{vazio ?? null}</>;
  return (
    <ul className="grid gap-2 md:grid-cols-2">
      {lista.map((a) => (
        <li key={a.id} className="rounded-lg border border-[var(--color-border)] p-3 grid gap-2 content-between min-w-0">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-medium break-words">{a.titulo}</span>
              <Selo estado={a.risco} rotulo={ROTULO_RISCO[a.risco]} />
            </div>
            <p className="text-xs text-[var(--color-text-secondary)] mt-1 break-words">{a.descricao}</p>
          </div>
          <div>
            <BotaoAcao acao={a} />
          </div>
        </li>
      ))}
    </ul>
  );
}
