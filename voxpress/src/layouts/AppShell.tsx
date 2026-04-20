import type { ReactNode } from 'react';
import { Outlet } from 'react-router-dom';
import { Toaster } from 'sonner';
import { Sidebar } from '@/components/Sidebar/Sidebar';
import { TweaksPanel } from '@/components/TweaksPanel/TweaksPanel';
import s from './AppShell.module.css';

export function AppShell() {
  return (
    <div className={s.shell}>
      <Sidebar />
      <main className={s.main}>
        <Outlet />
      </main>
      <TweaksPanel />
      <Toaster position="bottom-right" />
    </div>
  );
}

export function Page({ children }: { children: ReactNode }) {
  return <div className={s.page}>{children}</div>;
}

export function PageHead({ title, meta }: { title: ReactNode; meta?: ReactNode }) {
  return (
    <header className={s.pageHead}>
      <h1 className={s.pageTitle}>{title}</h1>
      {meta ? <div className={s.pageMeta}>{meta}</div> : null}
    </header>
  );
}
