import type { ReactNode } from "react";

interface PageHeaderProps {
  title: string;
  meta?: ReactNode;
  right?: ReactNode;
}

export function PageHeader({ title, meta, right }: PageHeaderProps) {
  return (
    <div className="topbar">
      <div>
        <h1 className="page-title">{title}</h1>
        {meta && <div className="page-meta">{meta}</div>}
      </div>
      {right && <div className="topbar-right">{right}</div>}
    </div>
  );
}
