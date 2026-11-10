import { Pagina } from '../componentes/Pagina';
import { Cartao } from '../componentes/Cartao';
import { EstadoVazio } from '../componentes/EstadoVazio';
import { Hammer } from 'lucide-react';

/** Texto padrao das paginas provisorias. Cada frente de tela troca a sua pagina inteira. */
export function Provisoria({ titulo }: { titulo: string }) {
  return (
    <Pagina titulo={titulo}>
      <Cartao>
        <EstadoVazio icone={<Hammer size={32} aria-hidden="true" />} titulo="Esta tela ainda está sendo feita" texto="Em breve ela aparece aqui." />
      </Cartao>
    </Pagina>
  );
}
