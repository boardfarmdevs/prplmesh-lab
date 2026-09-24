import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import Explorer from './app/page';
import '@fontsource-variable/geist';
import '@fontsource-variable/geist-mono';
import './app/globals.css';
import './app/navigation.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <nav className="site-navigation" aria-label="Lab documentation">
      <a href="../">Lab home</a>
      <a href="./" aria-current="page">
        System explorer
      </a>
      <a href="../viewer/">Room viewer</a>
      <a href="../viewer/manual.html">Manual</a>
    </nav>
    <Explorer />
  </StrictMode>,
);
