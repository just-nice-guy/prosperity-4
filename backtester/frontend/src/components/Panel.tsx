import { PropsWithChildren, ReactNode } from "react";

type PanelProps = PropsWithChildren<{
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}>;

export function Panel({ title, subtitle, actions, children }: PanelProps) {
  return (
    <section className="panel">
      <header className="panel-header">
        <div className="panel-header-left">
          <p className="panel-eyebrow">{subtitle ?? "Module"}</p>
          <p className="panel-title">{title}</p>
        </div>
        {actions ? <div>{actions}</div> : null}
      </header>
      <div className="panel-body">{children}</div>
    </section>
  );
}
