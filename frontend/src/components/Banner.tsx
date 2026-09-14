import type { ReactNode } from "react";

interface BannerProps {
  kind: "error" | "success" | "warn";
  children: ReactNode;
}

export function Banner({ kind, children }: BannerProps) {
  return <div className={`banner banner-${kind}`}>{children}</div>;
}
