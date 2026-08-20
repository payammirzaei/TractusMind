const baseUrl = (process.env.SMOKE_BASE_URL ?? "http://127.0.0.1:3100").replace(/\/$/, "");

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

const status = await fetch(`${baseUrl}/api/oidc/status`, { cache: "no-store" });
const payload = await status.json();
assert(status.status === 200, `OIDC status returned ${status.status}`);
assert(payload.enabled === false, "OIDC unexpectedly enabled without explicit runtime enablement");
assert(payload.login_path === null, "disabled OIDC exposed a login path");
process.stdout.write("ok OIDC disabled status fails closed\n");

const login = await fetch(`${baseUrl}/api/oidc/login`, { redirect: "manual", cache: "no-store" });
assert(login.status >= 300 && login.status < 400, `disabled OIDC login returned ${login.status}`);
const location = login.headers.get("location") ?? "";
assert(location.includes("auth_error=sso_not_configured"), `disabled OIDC login did not fail closed: ${location}`);
process.stdout.write("ok disabled OIDC login rejected\n");

process.stdout.write("Mission Control disabled-OIDC smoke passed.\n");
