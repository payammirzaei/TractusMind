const baseUrl = (process.env.SMOKE_BASE_URL ?? "http://127.0.0.1:3100").replace(/\/$/, "");
const token = "tm_test_admin";

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function body(response) {
  const text = await response.text();
  try { return JSON.parse(text); } catch { return text; }
}

async function authenticatedGet(path, cookie) {
  const response = await fetch(`${baseUrl}${path}`, { headers: { cookie }, cache: "no-store" });
  const payload = await body(response);
  assert(response.status === 200, `${path} returned ${response.status}: ${JSON.stringify(payload)}`);
  return payload;
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

const summaryPayload = await authenticatedGet("/api/backend/v1/ops/summary", cookie);
assert(summaryPayload.indexed_sources === 1, "ops summary payload was not forwarded");
process.stdout.write("ok ops summary contract\n");

const sourcesPayload = await authenticatedGet("/api/backend/v1/ops/sources", cookie);
assert(Array.isArray(sourcesPayload) && sourcesPayload[0]?.source_id === "tractusx-sdk", "sources contract was not forwarded");
process.stdout.write("ok source fleet contract\n");

const runsPayload = await authenticatedGet("/api/backend/v1/ops/runs?limit=24", cookie);
assert(Array.isArray(runsPayload), "runs contract was not forwarded");
process.stdout.write("ok ingestion runs contract\n");

const qualitySummary = await authenticatedGet("/api/backend/v1/ops/quality/summary", cookie);
assert(qualitySummary.regression_cases === 1, "quality summary contract was not forwarded");
process.stdout.write("ok quality summary contract\n");

const qualityReviews = await authenticatedGet("/api/backend/v1/ops/quality/reviews?limit=8", cookie);
assert(Array.isArray(qualityReviews), "quality reviews contract was not forwarded");
process.stdout.write("ok quality review contract\n");

const health = await fetch(`${baseUrl}/api/backend/health/ready`, { cache: "no-store" });
const healthPayload = await body(health);
assert(health.status === 200 && healthPayload.checks?.qdrant === "ok", "health proxy did not forward readiness payload");
process.stdout.write("ok unauthenticated health proxy\n");

const anonymousOps = await fetch(`${baseUrl}/api/backend/v1/ops/summary`, { cache: "no-store" });
assert(anonymousOps.status === 401, `anonymous ops proxy returned ${anonymousOps.status}`);
process.stdout.write("ok anonymous ops request rejected upstream\n");

const blockedPath = await fetch(`${baseUrl}/api/backend/v1/internal/secrets`, { headers: { cookie }, cache: "no-store" });
assert(blockedPath.status === 404, `unsupported backend path returned ${blockedPath.status}`);
process.stdout.write("ok backend proxy allowlist enforced\n");

const blockedHealthMutation = await fetch(`${baseUrl}/api/backend/health/ready`, { method: "POST", headers: { cookie } });
assert(blockedHealthMutation.status === 405, `health mutation returned ${blockedHealthMutation.status}`);
process.stdout.write("ok health proxy remains read-only\n");

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
