const baseUrl = (process.env.SMOKE_BASE_URL ?? "http://127.0.0.1:3100").replace(/\/$/, "");
const token = "tm_test_admin";

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function body(response) {
  const text = await response.text();
  try { return JSON.parse(text); } catch { return text; }
}

const crossSite = await fetch(`${baseUrl}/api/session`, {
  method: "POST",
  headers: {
    "content-type": "application/json",
    "origin": "https://evil.example",
    "sec-fetch-site": "cross-site",
  },
  body: JSON.stringify({ token }),
});
assert(crossSite.status === 403, `cross-site session mutation returned ${crossSite.status}`);
process.stdout.write("ok cross-site session mutation rejected\n");

const login = await fetch(`${baseUrl}/api/session`, {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify({ token }),
});
const loginPayload = await body(login);
assert(login.status === 200, `session login returned ${login.status}: ${JSON.stringify(loginPayload)}`);
assert(loginPayload.role === "admin", "session identity role was not forwarded");

const setCookie = login.headers.get("set-cookie") ?? "";
assert(setCookie.includes("__Host-tm_session="), "production session cookie name is not __Host-prefixed");
assert(/HttpOnly/i.test(setCookie), "session cookie is missing HttpOnly");
assert(/Secure/i.test(setCookie), "session cookie is missing Secure");
assert(/SameSite=Lax/i.test(setCookie), "session cookie is missing SameSite=Lax");
assert(/Path=\//i.test(setCookie), "session cookie is missing Path=/");
const cookie = setCookie.split(";")[0];
process.stdout.write("ok secure HttpOnly session established\n");

const me = await fetch(`${baseUrl}/api/session`, { headers: { cookie }, cache: "no-store" });
const mePayload = await body(me);
assert(me.status === 200, `session read returned ${me.status}`);
assert(mePayload.display_name === "CI Admin", "session identity did not survive cookie round-trip");
process.stdout.write("ok session identity round-trip\n");

const summary = await fetch(`${baseUrl}/api/backend/v1/ops/summary`, { headers: { cookie }, cache: "no-store" });
const summaryPayload = await body(summary);
assert(summary.status === 200, `ops proxy returned ${summary.status}: ${JSON.stringify(summaryPayload)}`);
assert(summaryPayload.indexed_sources === 1, "ops proxy payload was not forwarded");
process.stdout.write("ok authenticated backend GET proxy\n");

const health = await fetch(`${baseUrl}/api/backend/health/ready`, { cache: "no-store" });
const healthPayload = await body(health);
assert(health.status === 200 && healthPayload.checks?.qdrant === "ok", "health proxy did not forward readiness payload");
process.stdout.write("ok unauthenticated health proxy\n");

const blockedMutation = await fetch(`${baseUrl}/api/backend/v1/ops/sync`, {
  method: "POST",
  headers: {
    cookie,
    origin: "https://evil.example",
    "sec-fetch-site": "cross-site",
  },
});
assert(blockedMutation.status === 403, `cross-site backend mutation returned ${blockedMutation.status}`);
process.stdout.write("ok cross-site backend mutation rejected\n");

const sync = await fetch(`${baseUrl}/api/backend/v1/ops/sync`, {
  method: "POST",
  headers: { cookie },
});
const syncPayload = await body(sync);
assert(sync.status === 202, `same-site ops mutation returned ${sync.status}: ${JSON.stringify(syncPayload)}`);
assert(syncPayload.status === "queued", "ops mutation response was not forwarded");
process.stdout.write("ok authenticated backend mutation proxy\n");

const logout = await fetch(`${baseUrl}/api/session`, {
  method: "DELETE",
  headers: { cookie },
});
assert(logout.status === 200, `logout returned ${logout.status}`);
const clearCookie = logout.headers.get("set-cookie") ?? "";
assert(/Max-Age=0/i.test(clearCookie), "logout did not expire the session cookie");
process.stdout.write("ok session logout expiry\n");

const anonymous = await fetch(`${baseUrl}/api/session`, { cache: "no-store" });
assert(anonymous.status === 401, `anonymous session check returned ${anonymous.status}`);
process.stdout.write("ok anonymous session rejected\n");

process.stdout.write("Mission Control BFF smoke passed.\n");
