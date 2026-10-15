import React from 'react';
import { cx } from './cn';

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger';
type Size = 'sm' | 'md';

const base =
  'inline-flex items-center justify-center gap-2 rounded-lg font-semibold transition-colors disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer whitespace-nowrap';

const variants: Record<Variant, string> = {
  primary: 'bg-accent text-white hover:bg-accent-hover',
  secondary: 'bg-surface-2 text-fg border border-line-strong hover:border-accent/60',
  ghost: 'text-fg-2 hover:text-fg hover:bg-surface-2',
  danger: 'bg-bad-soft text-bad border border-bad/30 hover:bg-bad/20',
};

const sizes: Record<Size, string> = {
  sm: 'h-8 px-3 text-xs',
  md: 'h-10 px-4 text-sm',
};

/** Class string for links or custom elements that should look like buttons. */
export function buttonClass(variant: Variant = 'primary', size: Size = 'md', extra?: string) {
  return cx(base, variants[variant], sizes[size], extra);
}

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
}

export function Button({ variant = 'primary', size = 'md', className, type = 'button', ...rest }: ButtonProps) {
  return <button type={type} className={buttonClass(variant, size, className)} {...rest} />;
}
