export default function Loading() {
  return (
    <main className="grid min-h-screen place-items-center p-5">
      <div className="tm-shell relative w-full max-w-[620px] rounded-[28px] p-3">
        <span className="tm-screw absolute left-4 top-4"/><span className="tm-screw absolute right-4 top-4"/><span className="tm-screw absolute bottom-4 left-4"/><span className="tm-screw absolute bottom-4 right-4"/>
        <div className="tm-well rounded-[20px] p-7 sm:p-9">
          <div className="flex items-center gap-3"><span className="tm-led cyan"/><span className="tm-label">routing mission surface</span></div>
          <div className="mt-7 space-y-3">
            <div className="h-7 w-2/5 animate-pulse rounded-lg bg-white/[.045]"/>
            <div className="h-4 w-3/4 animate-pulse rounded bg-white/[.025]"/>
            <div className="grid grid-cols-2 gap-3 pt-3 sm:grid-cols-4">{Array.from({ length: 4 }).map((_, index) => <div key={index} className="h-24 animate-pulse rounded-xl border border-white/[.035] bg-white/[.018]"/>)}</div>
          </div>
        </div>
      </div>
    </main>
  );
}
