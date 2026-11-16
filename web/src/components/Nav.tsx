import { Link } from 'react-router-dom';
import type { ReactNode } from 'react';
import { LogoMini, Wordmark } from './Logo';

export function Nav({ children }: { children?: ReactNode }) {
  return (
    <header className="wrap">
      <nav aria-label="Primary" className="nav">
        <Link to="/" aria-label="Cuepoint home" className="nav-brand">
          <LogoMini />
          <Wordmark />
        </Link>
        <div className="nav-links mono-label">{children}</div>
      </nav>
    </header>
  );
}
