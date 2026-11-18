import { Puzzle } from 'lucide-react';
import { useRef, useState } from 'react';
import { usePlugins, useMudarPlugin } from '../../api/ganchos';
import type { Plugin } from '../../api/tipos';
import { Botao, Cartao, Erro, EsqueletoPagina, EstadoVazio, useAvisos } from '../../componentes';
import {
  TEXTO_CONFLITO, TEXTO_FIXO, TEXTO_SUCESSO, TEXTO_VAZIO, TIPO_ARRASTE,
  avisoSobreposto, botaoDoPlugin, criarMovedor, dividirColunas, origemDoValor, pesoEstimado, podeArrastar, detalheSucesso,
} from './plugins-logica';

export default function Plugins() {
  const estado = usePlugins();
  const mudar = useMudarPlugin();
  const { avisar } = useAvisos();
  const [pendente, setPendente] = useState<string | null>(null);
  const [sobre, setSobre] = useState<boolean | null>(null);
  // O movedor vive entre renders (guarda de envio unico); as funcoes sempre vem do render mais novo.
  const vivo = useRef({ mudar, avisar, refazer: estado.refetch });
  vivo.current = { mudar, avisar, refazer: estado.refetch };
  const movedor = useRef(
    criarMovedor({
      enviar: (id, enabled) => vivo.current.mudar.mutateAsync({ id, enabled }),
      aoOcupar: setPendente,
      aoSucesso: (r, id) => vivo.current.avisar({ tipo: 'sucesso', titulo: TEXTO_SUCESSO, texto: detalheSucesso(r, id) }),
      aoConflito: (m) => {
        vivo.current.avisar({ tipo: 'atencao', titulo: TEXTO_CONFLITO, texto: m });
        void vivo.current.refazer();
      },
      aoErro: (m) => vivo.current.avisar({ tipo: 'erro', titulo: 'Não deu para mudar o plugin', texto: m }),
    }),
  ).current;

  if (estado.isPending) return <section aria-label="Plugins"><EsqueletoPagina cartoes={2} /></section>;
  if (estado.isError) return <section aria-label="Plugins"><Erro erro={estado.error} aoTentar={() => void estado.refetch()} /></section>;

  const { plugins, aviso } = estado.data;
  const { ligados, desligados } = dividirColunas(plugins);

  const coluna = (titulo: string, ligar: boolean, lista: Plugin[]) => (
    <div
      className={`rounded-lg border p-3 min-h-24 grid gap-3 content-start ${sobre === ligar ? 'border-[var(--color-accent)]' : 'border-[var(--color-border)]'}`}
      aria-label={titulo}
      onDragOver={(e) => {
        if (!e.dataTransfer.types.includes(TIPO_ARRASTE)) return;
        e.preventDefault();
        setSobre(ligar);
      }}
      onDragLeave={() => setSobre(null)}
      onDrop={(e) => {
        e.preventDefault();
        setSobre(null);
        const id = e.dataTransfer.getData(TIPO_ARRASTE);
        const p = plugins.find((x) => x.id === id);
        if (p && podeArrastar(p) && p.ligado !== ligar) void movedor(p.id, ligar);
      }}
    >
      <h4 className="text-xs font-semibold uppercase">{titulo} ({lista.length})</h4>
      {lista.map((p) => {
        const botao = botaoDoPlugin(p);
        const meu = pendente === p.id;
        const sobreposto = avisoSobreposto(p);
        return (
          <div
            key={p.id}
            draggable={podeArrastar(p) && pendente === null}
            onDragStart={(e) => {
              e.dataTransfer.setData(TIPO_ARRASTE, p.id);
              e.dataTransfer.effectAllowed = 'move';
            }}
            className={pendente !== null && !meu ? 'opacity-60' : ''}
          >
            <Cartao titulo={p.id} icone={<Puzzle size={16} aria-hidden="true" />}>
              <p className="text-xs">{pesoEstimado(p)}</p>
              <p className="mt-1 text-xs opacity-80">{origemDoValor(p)}</p>
              {sobreposto && <p className="mt-2 text-xs">{sobreposto}</p>}
              {p.fixo ? (
                <p className="mt-2 text-xs">{TEXTO_FIXO}</p>
              ) : (
                <div className="mt-3">
                  <Botao
                    variante={botao.variante}
                    enviando={meu}
                    textoEnviando={botao.textoEnviando}
                    disabled={pendente !== null && !meu}
                    onClick={() => void movedor(p.id, botao.pedir)}
                  >
                    {botao.texto}
                  </Botao>
                </div>
              )}
            </Cartao>
          </div>
        );
      })}
    </div>
  );

  return (
    <section aria-label="Plugins" className="mt-8">
      <h2 className="text-base font-semibold">Plugins</h2>
      <p className="text-sm opacity-80 mb-3">Seus plugins do Claude Code. Arraste o cartão para a outra coluna ou use o botão. Vale na próxima sessão.</p>
      {aviso && <p className="mb-3 text-xs" role="status">{aviso}</p>}
      {plugins.length === 0 ? (
        <EstadoVazio titulo={TEXTO_VAZIO} />
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {coluna('Ligado', true, ligados)}
          {coluna('Desligado', false, desligados)}
        </div>
      )}
    </section>
  );
}
