import type { Metadata } from "next";
import { headers } from "next/headers";
import "./globals.css";
import "./console.css";
import "./command-center.css";
import "./responsive.css";
import "./polish.css";

export const metadata: Metadata = {
  title: "TractusMind Mission Control",
  description: "Inspect, operate, and trust the TractusMind engineering copilot.",
};

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  // Nonce-based CSP requires request-time rendering so Next.js can propagate
  // the per-request nonce from the proxy policy onto its hydration scripts.
  await headers();

  return (
    <html lang="en" suppressHydrationWarning>
      <body>{children}</body>
    </html>
  );
}
