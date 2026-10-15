import React from 'react';
import { cx } from './cn';

/** Honest empty / unavailable state. Never fill gaps with invented data. */
export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
}: {
  icon?: React.ElementType;
  title: React.ReactNode;
  description?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cx(
        'flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-line-strong bg-inset px-6 py-10 text-center',
        className,
      )}
    >
      {Icon && <Icon className="h-6 w-6 text-subtle" strokeWidth={1.7} />}
      <p className="text-sm font-semibold text-fg">{title}</p>
      {description && <p className="max-w-md text-xs text-muted">{description}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}
