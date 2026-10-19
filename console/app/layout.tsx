import type { Metadata } from "next";
import Link from "next/link";
import { Suspense, type ReactNode } from "react";
import { TimeTravel } from "@/components/TimeTravel";
import "./globals.css";

export const metadata: Metadata = {
  title: "Abhiyogah console",
  description: "RBI complaint-compliance deadlines, breaches and decision records.",
};

/** The admin time-travel control is on unless `ABHIYOGAH_TIME_TRAVEL=off`. */
function timeTravelEnabled(): boolean {
  return process.env.ABHIYOGAH_TIME_TRAVEL !== "off";
}

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
          {timeTravelEnabled() && (
            <Suspense fallback={null}>
              <TimeTravel />
            </Suspense>
          )}
        </header>
        <main>{children}</main>
      </body>
    </html>
  );
}
