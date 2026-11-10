import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './index.css';
import { App } from './App';
import { Provedores } from './provedores';
import { iniciarTema } from './tema/tema';

iniciarTema(); // antes do primeiro desenho, para nao piscar

createRoot(document.getElementById('root') as HTMLElement).render(
  <StrictMode>
    <Provedores>
      <App />
    </Provedores>
  </StrictMode>,
);
