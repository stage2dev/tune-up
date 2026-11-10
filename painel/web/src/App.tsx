// Rotas. Cada pagina vive em arquivo proprio (src/paginas/...): as frentes de tela
// trocam so o arquivo da sua pagina e nao mexem aqui.
import { BrowserRouter, Navigate, Route, Routes } from 'react-router';
import { Layout } from './Layout';
import Inicio from './paginas/Inicio';
import Chat from './paginas/chat/Chat';
import Conversa from './paginas/chat/Conversa';
import Fases from './paginas/dev/Fases';
import Execucoes from './paginas/dev/Execucoes';
import ExecucaoDetalhe from './paginas/dev/ExecucaoDetalhe';
import Agentes from './paginas/agentes/Agentes';
import Modulo from './paginas/modulo/Modulo';
import Acompanhamento from './paginas/acompanhamento/Acompanhamento';

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Chat />} />
          <Route path="conversa/:id" element={<Conversa />} />
          <Route path="resumo" element={<Inicio />} />
          <Route path="fases" element={<Fases />} />
          <Route path="execucoes" element={<Execucoes />} />
          <Route path="execucoes/:id" element={<ExecucaoDetalhe />} />
          <Route path="agentes" element={<Agentes />} />
          <Route path="m/:id" element={<Modulo />} />
          <Route path="acompanhamento" element={<Acompanhamento />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
