import { Blocks } from 'lucide-react';
import { useState } from 'react';
import { useEmbutidos, useLigarEmbutido } from '../../api/ganchos';
import type { Embutido } from '../../api/tipos';
import { Botao, Cartao, Erro, EsqueletoPagina, EstadoVazio, Pagina, useAvisos } from '../../componentes';
import { botaoDoEmbutido, motivoBloqueio, rotuloEstado, textoEnviando, textoFalha, textoSucesso, tituloFalha } from './logica';

const TITULO = 'Módulos';
const SUBTITULO = 'Partes extras que já vêm com o tune-up. Ligue só o que for usar.';

export default function Modulos() {
  const estado = useEmbutidos();
  const ligar = useLigarEmbutido();
  const { avisar } = useAvisos();
  const [pendente, setPendente] = useState<string | null>(null);

  if (estado.isPending) return <Pagina titulo={TITULO} subtitulo={SUBTITULO}><EsqueletoPagina cartoes={2} /></Pagina>;
  if (estado.isError) return <Pagina titulo={TITULO} subtitulo={SUBTITULO}><Erro erro={estado.error} aoTentar={() => void estado.refetch()} /></Pagina>;

  const clicar = async (e: Embutido, pedir: boolean) => {
    if (pendente) return;
    setPendente(e.id);
    try {
      await ligar.mutateAsync({ id: e.id, ligado: pedir });
      avisar({ tipo: 'sucesso', titulo: textoSucesso(e.titulo, pedir) });
    } catch (erro) {
      avisar({ tipo: 'erro', titulo: tituloFalha(pedir), texto: textoFalha(erro) });
    } finally {
      setPendente(null);
    }
  };

  return (
    <Pagina titulo={TITULO} subtitulo={SUBTITULO}>
      {estado.data.length === 0 ? (
        <EstadoVazio titulo="Nenhuma parte extra por aqui" texto="Quando o tune-up trouxer partes extras, elas aparecem nesta tela." />
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {estado.data.map((e) => {
            const botao = botaoDoEmbutido(e);
            const bloqueio = motivoBloqueio(e);
            const meu = pendente === e.id;
            return (
              <Cartao key={e.id} titulo={e.titulo} icone={<Blocks size={16} aria-hidden="true" />} acao={<span className="text-xs">{rotuloEstado(e)}</span>}>
                <p className="text-sm">{e.descricao}</p>
                {e.avisos.map((a) => (
                  <p key={a} className="mt-2 text-xs opacity-80">{a}</p>
                ))}
                {bloqueio && <p className="mt-2 text-xs">{bloqueio}</p>}
                <div className="mt-3">
                  <Botao
                    variante={botao.variante}
                    enviando={meu}
                    textoEnviando={textoEnviando(botao.pedir)}
                    disabled={bloqueio !== null || (pendente !== null && !meu)}
                    onClick={() => void clicar(e, botao.pedir)}
                  >
                    {botao.texto}
                  </Botao>
                </div>
              </Cartao>
            );
          })}
        </div>
      )}
    </Pagina>
  );
}
