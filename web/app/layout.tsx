import type { Metadata, Viewport } from "next";
import { GeistMono } from "geist/font/mono";
import Link from "next/link";

import { getMeta } from "@/lib/data";
import { month } from "@/lib/format";
import { AUTHOR, REPO_URL } from "@/lib/site";

import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "unbundle · did your fund manager earn their fee?",
    template: "%s · unbundle",
  },
  description:
    "For well-known equity funds and ETFs: how much of the last ten years' return was cheap " +
    "factor exposure, and how much was alpha after fees.",
  authors: [{ name: AUTHOR }],
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#0a0a0a" },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const meta = getMeta();
  return (
    <html lang="en" className={GeistMono.variable}>
      <body className="min-h-dvh">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:border focus:border-fg focus:bg-bg focus:px-2 focus:py-1"
        >
          skip to content
        </a>
        <div className="mx-auto flex min-h-dvh w-full max-w-5xl flex-col px-4 sm:px-6">
          <header className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2 py-6">
            <Link href="/" className="plain font-medium">
              unbundle
            </Link>
            <nav aria-label="main" className="flex gap-5 text-sm text-muted">
              <Link href="/">funds</Link>
              <Link href="/method">method</Link>
              <a href={REPO_URL}>source</a>
            </nav>
          </header>
          <main id="main" className="flex-1 pb-20">
            {children}
          </main>
          <footer className="flex flex-col gap-1 border-t border-line py-8 text-sm text-muted sm:flex-row sm:justify-between">
            <p>
              built by {AUTHOR} · <a href={REPO_URL}>source on GitHub</a>
            </p>
            <p>
              data through {month(meta.through)} ·{" "}
              <span className="whitespace-nowrap">updated {meta.generated_at}</span>
            </p>
          </footer>
        </div>
      </body>
    </html>
  );
}
