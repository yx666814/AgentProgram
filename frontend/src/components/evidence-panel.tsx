import type { PropsWithChildren } from "react";

export type EvidencePanelProps = PropsWithChildren<{
  open: boolean;
  title: string;
}>;

export function EvidencePanel({ children, open, title }: EvidencePanelProps) {
  if (!open) {
    return null;
  }
  return (
    <aside aria-label={title} className="evidence-panel">
      <h2>{title}</h2>
      {children}
    </aside>
  );
}
