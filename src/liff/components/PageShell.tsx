import type { ReactNode } from "react";
import { Flame } from "lucide-react";
import LanguageSwitcher from "./LanguageSwitcher";

type PageShellProps = {
  title: string;
  subtitle: string;
  children: ReactNode;
};

export default function PageShell({ title, subtitle, children }: PageShellProps) {
  return (
    <div className="report-shell">
      <header className="report-header">
        <div className="report-header-inner">
          <div className="brand-icon" aria-hidden="true">
            <Flame size={20} />
          </div>
          <div>
            <h1>{title}</h1>
            <p>{subtitle}</p>
          </div>
          <LanguageSwitcher />
        </div>
      </header>
      <main className="report-page">{children}</main>
    </div>
  );
}
