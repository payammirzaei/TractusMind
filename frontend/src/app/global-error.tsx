"use client";

import { AlertTriangle, RotateCw } from "lucide-react";

export default function GlobalError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <html lang="en">
      <body style={{ margin: 0, minHeight: "100vh", background: "#090b0d", color: "#e9eef2", fontFamily: "Arial, Helvetica, sans-serif" }}>
        <main style={{ minHeight: "100vh", display: "grid", placeItems: "center", padding: 24 }}>
          <div style={{ width: "100%", maxWidth: 560, border: "1px solid rgba(255,255,255,.08)", borderRadius: 24, padding: 28, background: "linear-gradient(145deg,#1b2025,#0b0e11)", boxShadow: "0 30px 80px rgba(0,0,0,.45)" }}>
            <AlertTriangle size={26} color="#ff7474"/>
            <div style={{ marginTop: 20, fontSize: 10, letterSpacing: ".16em", textTransform: "uppercase", color: "#ff9a9a", fontWeight: 700 }}>root fail-safe</div>
            <h1 style={{ margin: "10px 0 0", fontSize: 26, letterSpacing: "-.03em" }}>Mission Control could not initialize.</h1>
            <p style={{ marginTop: 14, color: "#87939d", fontSize: 14, lineHeight: 1.7 }}>A root-level frontend failure was contained before an unsafe or partially initialized console could be shown.</p>
            <button onClick={reset} style={{ marginTop: 22, minHeight: 40, padding: "0 16px", borderRadius: 10, border: "1px solid rgba(115,232,255,.2)", background: "#171b1f", color: "#dffaff", fontWeight: 700, cursor: "pointer", display: "inline-flex", alignItems: "center", gap: 8 }}><RotateCw size={15}/>Retry initialization</button>
          </div>
        </main>
      </body>
    </html>
  );
}
