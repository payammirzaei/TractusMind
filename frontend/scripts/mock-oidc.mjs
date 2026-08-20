import { createHash, randomBytes } from "node:crypto";
import http from "node:http";

const host = process.env.MOCK_OIDC_HOST ?? "127.0.0.1";
const port = Number(process.env.MOCK_OIDC_PORT ?? 8001);
const publicOrigin = process.env.MOCK_OIDC_ORIGIN ?? `http://127.0.0.1:${port}`;
const clientId = "tractusmind-ci";
const codes = new Map();

function json(response, status, payload) {
  response.writeHead(status, { "content-type": "application/json", "cache-control": "no-store" });
  response.end(JSON.stringify(payload));
}

function redirect(response, location) {
  response.writeHead(302, { location, "cache-control": "no-store" });
  response.end();
}

async function readBody(request) {
  const chunks = [];
  for await (const chunk of request) chunks.push(chunk);
  return Buffer.concat(chunks).toString("utf8");
}

const server = http.createServer(async (request, response) => {
  const url = new URL(request.url ?? "/", publicOrigin);

  if (request.method === "GET" && url.pathname === "/.well-known/openid-configuration") {
    return json(response, 200, {
      issuer: publicOrigin,
      authorization_endpoint: `${publicOrigin}/authorize`,
      token_endpoint: `${publicOrigin}/token`,
      response_types_supported: ["code"],
      grant_types_supported: ["authorization_code"],
      code_challenge_methods_supported: ["S256"],
    });
  }

  if (request.method === "GET" && url.pathname === "/authorize") {
    const incomingClient = url.searchParams.get("client_id");
    const redirectUri = url.searchParams.get("redirect_uri");
    const state = url.searchParams.get("state");
    const challenge = url.searchParams.get("code_challenge");
    const method = url.searchParams.get("code_challenge_method");
    if (incomingClient !== clientId || !redirectUri || !state || !challenge || method !== "S256") {
      return json(response, 400, { error: "invalid_request" });
    }
    const code = randomBytes(18).toString("base64url");
    codes.set(code, { challenge, redirectUri, clientId: incomingClient });
    const callback = new URL(redirectUri);
    callback.searchParams.set("code", code);
    callback.searchParams.set("state", state);
    return redirect(response, callback.toString());
  }

  if (request.method === "POST" && url.pathname === "/token") {
    const form = new URLSearchParams(await readBody(request));
    const code = form.get("code") ?? "";
    const verifier = form.get("code_verifier") ?? "";
    const stored = codes.get(code);
    const challenge = createHash("sha256").update(verifier).digest("base64url");
    const valid = stored &&
      form.get("grant_type") === "authorization_code" &&
      form.get("client_id") === stored.clientId &&
      form.get("redirect_uri") === stored.redirectUri &&
      challenge === stored.challenge;
    if (!valid) return json(response, 400, { error: "invalid_grant" });
    codes.delete(code);
    return json(response, 200, {
      access_token: "tm_test_admin",
      token_type: "Bearer",
      expires_in: 1800,
      scope: "openid profile email",
    });
  }

  return json(response, 404, { error: "not_found" });
});

server.listen(port, host, () => {
  process.stdout.write(`mock oidc listening on ${host}:${port}\n`);
});

function shutdown() {
  server.close(() => process.exit(0));
}

process.on("SIGTERM", shutdown);
process.on("SIGINT", shutdown);
