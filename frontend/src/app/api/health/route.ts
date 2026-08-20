export function GET() {
  return Response.json(
    { status: "ok", service: "tractusmind-mission-control" },
    { headers: { "cache-control": "no-store, max-age=0" } },
  );
}
