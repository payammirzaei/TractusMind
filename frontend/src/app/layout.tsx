import type { Metadata } from "next";
import { headers } from "next/headers";
import "./globals.css";
import "./console.css";
import "./command-center.css";
import "./responsive.css";
import "./polish.css";
import "./theme.css";

export const metadata: Metadata = {
  title: "TractusMind Mission Control",
  description: "Inspect, operate, and trust the TractusMind engineering copilot.",
};

// Static, request-independent script: only reads a same-origin localStorage flag,
// never reflects request/user input, so no injection surface despite dangerouslySetInnerHTML.
const THEME_INIT_SCRIPT = `(function(){try{var t=localStorage.getItem('tm-theme')==='light'?'light':'dark';document.documentElement.setAttribute('data-theme',t);}catch(e){}})();`;

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  // Nonce-based CSP requires request-time rendering so Next.js can propagate
  // the per-request nonce from the proxy policy onto its hydration scripts.
  const nonce = (await headers()).get("x-nonce") ?? undefined;

  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <script nonce={nonce} dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
        {children}
      </body>
    </html>
  );
}
