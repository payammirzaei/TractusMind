import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "TractusMind Mission Control",
  description: "Inspect, operate, and trust the TractusMind engineering copilot.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>{children}</body>
    </html>
  );
}
