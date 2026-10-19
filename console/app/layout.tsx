import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: "Abhiyogah console",
  description: "RBI complaint-compliance deadlines, breaches and decision records.",
};

/** Root layout shared by every console page. */
export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en-IN">
      <body>
        <header className="topbar">
          <span className="brand">Abhiyogah</span>
          <nav aria-label="Main">
            <Link href="/">Deadline board</Link>
            <Link href="/rules">Rule browser</Link>
          </nav>
        </header>
        <main>{children}</main>
      </body>
    </html>
  );
}
