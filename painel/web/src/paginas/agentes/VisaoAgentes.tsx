// Parte da tela que so desenha (sem busca): resumo + arvore de sessoes. Testada em render.test.ts.
import type { RespostaAgentes } from '../../api/agentes';
import { EstadoVazio } from '../../componentes';
import { CartaoSessao, type Recolhimento } from './CartaoSessao';
import { resumir } from './logica';
import { FaixaResumo } from './Resumo';

export function AvisosAgentes({ avisos }: { avisos: string[] }) {
  if (avisos.length === 0) return null;
  return (
    <details className="text-xs text-[var(--color-text-secondary)]">
      <summary className="cursor-pointer">{avisos.length === 1 ? '1 aviso sobre a leitura dos agentes' : `${avisos.length} avisos sobre a leitura dos agentes`}</summary>
      <ul className="mt-2 grid grid-cols-1 gap-1 list-disc pl-4">
        {avisos.map((a, i) => <li key={i} className="break-words">{a}</li>)}
      </ul>
    </details>
  );
}

export function VisaoAgentes({ dados, agora, rec, todos }: { dados: RespostaAgentes; agora: number; rec: Recolhimento; todos: boolean }) {
  if (dados.sessoes.length === 0) {
    return (
      <div className="grid gap-3">
        <AvisosAgentes avisos={dados.avisos} />
        <EstadoVazio
          titulo="Nenhuma sessão do Claude neste projeto agora"
          texto={
            todos
              ? 'Quando você abrir o Claude nesta pasta, ou o painel colocar uma Parte para rodar, ela aparece aqui sozinha.'
              : 'Quando você abrir o Claude nesta pasta, ou o painel colocar uma Parte para rodar, ela aparece aqui sozinha. Para ver as que já pararam, escolha "Todos".'
          }
        />
      </div>
    );
  }
  return (
    <div className="grid gap-4">
      <FaixaResumo r={resumir(dados.sessoes)} />
      <AvisosAgentes avisos={dados.avisos} />
      <div className="grid gap-3">
        {dados.sessoes.map((s) => <CartaoSessao key={s.id} s={s} agora={agora} rec={rec} />)}
      </div>
    </div>
  );
}
