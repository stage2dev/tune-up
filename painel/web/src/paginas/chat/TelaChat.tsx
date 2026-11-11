// A tela de chat (uma so para "/" e "/conversa/:id"): conversas a esquerda, conversa + caixa no centro,
// "Quem esta trabalhando" a direita. No celular as laterais abrem em gaveta pelos botoes do topo.
import { useCallback, useEffect, useState } from 'react';
import { Link, useLocation, useParams } from 'react-router';
import { Bot, MessageSquare } from 'lucide-react';
import { useAcoes, useExecucoes, useHabilidades } from '../../api/ganchos';
import { Erro, EsqueletoPagina, EstadoVazio } from '../../componentes';
import { ConversaAberta } from './ConversaAberta';
import { Gaveta } from './Gaveta';
import { ColunaEsquerda, gravarAba, lerAba, type AbaLateral } from './ColunaEsquerda';
import { NovaConversa } from './NovaConversa';
import { PainelAgentes } from './PainelAgentes';
import { acoesDoChat, grupoDe, GRUPO_CHAT } from './logica';
import { useSkillsDoPedido } from './useSkillsDoPedido';

const botaoTopo =
  'inline-flex items-center gap-1.5 h-8 px-2.5 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] text-xs text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-tertiary)]';

export default function TelaChat() {
  const { id } = useParams();
  const { pathname } = useLocation();
  const acoes = useAcoes();
  const [gaveta, setGaveta] = useState<'conversas' | 'agentes' | null>(null);
  const fechar = useCallback(() => setGaveta(null), []);
  const [aba, setAba] = useState<AbaLateral>(lerAba);
  const trocarAba = (a: AbaLateral) => (setAba(a), gravarAba(a));
  const skills = useSkillsDoPedido();
  const { limpar, podar } = skills;
  useEffect(() => limpar(), [id, limpar]); // skills escolhidas valem por conversa
  const habilidades = useHabilidades().data?.habilidades;
  useEffect(() => {
    if (habilidades) podar(habilidades);
  }, [habilidades, podar]);
  // Mesmo criterio do servidor: so conversa do grupo chat aceita skills. Tela nova (ou lista ainda sem a conversa) aceita.
  const aberta = useExecucoes().data?.find((e) => e.id === id);
  const aceita = !id || !aberta || grupoDe(aberta) === GRUPO_CHAT;
  useEffect(() => setGaveta(null), [pathname]);

  const niveis = acoesDoChat(acoes.data);
  let centro;
  if (acoes.isPending) centro = <div className="p-4"><EsqueletoPagina cartoes={2} /></div>;
  else if (acoes.isError) centro = <div className="p-4"><Erro erro={acoes.error} aoTentar={() => void acoes.refetch()} /></div>;
  else if (id) centro = <ConversaAberta key={id} id={id} niveis={niveis} skills={skills} />;
  else if (niveis.length === 0) {
    centro = (
      <EstadoVazio
        icone={<MessageSquare size={32} aria-hidden="true" />}
        titulo="O chat ainda não está disponível"
        texto="Este painel não trouxe nenhum tipo de pedido para o chat. Atualize o painel para a versão nova e abra esta página de novo."
      >
        <Link to="/resumo" className="text-sm underline text-[var(--color-accent)]">Ver o resumo</Link>
      </EstadoVazio>
    );
  } else centro = <NovaConversa niveis={niveis} skills={skills} />;

  return (
    <div className="h-full flex min-w-0">
      <aside aria-label="Conversas e skills" className="hidden md:flex flex-col w-60 shrink-0 border-r border-[var(--color-border)] p-3 overflow-y-auto">
        <ColunaEsquerda aba={aba} aoTrocar={trocarAba} atual={id} niveis={niveis} skills={skills} aceitaSkills={aceita} />
      </aside>

      <section className="flex-1 min-w-0 flex flex-col">
        <div className="flex items-center gap-2 px-3 pt-3 md:hidden">
          <button type="button" className={botaoTopo} onClick={() => setGaveta('conversas')} aria-haspopup="dialog">
            <MessageSquare size={14} aria-hidden="true" />
            Conversas e skills
          </button>
          {id && (
            <button type="button" className={`${botaoTopo} ml-auto`} onClick={() => setGaveta('agentes')} aria-haspopup="dialog">
              <Bot size={14} aria-hidden="true" />
              Quem está trabalhando
            </button>
          )}
        </div>
        {id && (
          <div className="hidden md:flex lg:hidden justify-end px-3 pt-3">
            <button type="button" className={botaoTopo} onClick={() => setGaveta('agentes')} aria-haspopup="dialog">
              <Bot size={14} aria-hidden="true" />
              Quem está trabalhando
            </button>
          </div>
        )}
        <div className="flex-1 min-h-0 flex flex-col">{centro}</div>
      </section>

      {id && (
        <aside aria-label="Quem está trabalhando" className="hidden lg:flex flex-col w-80 shrink-0 border-l border-[var(--color-border)] p-3 overflow-y-auto">
          <PainelAgentes id={id} />
        </aside>
      )}

      <Gaveta aberta={gaveta === 'conversas'} lado="esq" titulo="Conversas e skills" aoFechar={fechar}>
        <ColunaEsquerda aba={aba} aoTrocar={trocarAba} atual={id} niveis={niveis} skills={skills} aceitaSkills={aceita} />
      </Gaveta>
      {id && (
        <Gaveta aberta={gaveta === 'agentes'} lado="dir" titulo="Quem está trabalhando" aoFechar={fechar}>
          <PainelAgentes id={id} />
        </Gaveta>
      )}
    </div>
  );
}
