import Link from 'next/link';
import { FileText } from 'lucide-react';
import { AppShell } from '@/components/AppShell';
import { EmptyState, buttonClass } from '@/components/ui';

/** The CV editor lives in Resume Studio; this legacy route points there instead of showing a placeholder. */
export default function ResumeEditor() {
  return (
    <AppShell>
      <EmptyState
        icon={FileText}
        title="The CV editor has moved"
        description="Edit, preview and export your CV in Resume Studio."
        action={<Link href="/resume" className={buttonClass('primary', 'sm')}>Open Resume Studio</Link>}
      />
    </AppShell>
  );
}
