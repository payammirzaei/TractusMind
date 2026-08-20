import { oidcConfig } from "@/lib/server-oidc";

export async function GET() {
  const config = oidcConfig();
  return Response.json(
    {
      enabled: config.enabled,
      login_path: config.enabled ? "/api/oidc/login" : null,
    },
    { headers: { "cache-control": "no-store, max-age=0" } },
  );
}
