import React from 'react';
import { cx } from './cn';

export function Card({ className, children, ...rest }: React.HTMLAttributes<HTMLElement>) {
  return (
    <section className={cx('bg-surface border border-line rounded-lg p-4 sm:p-5', className)} {...rest}>
      {children}
    </section>
  );
}

export function CardHeader({
  title,
  note,
  action,
  className,
}: {
  title: React.ReactNode;
  note?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <header className={cx('flex flex-wrap items-center gap-x-3 gap-y-1 mb-4', className)}>
      <h2 className="text-base font-semibold tracking-tight text-fg">{title}</h2>
      {note && <span className="text-xs text-muted">{note}</span>}
      {action && <div className="ml-auto">{action}</div>}
    </header>
  );
}
