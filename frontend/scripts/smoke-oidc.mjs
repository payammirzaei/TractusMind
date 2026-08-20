const baseUrl = (process.env.SMOKE_BASE_URL ?? "http://127.0.0.1:3100").replace(/\/$/, "");

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function cookiesFrom(response) {
  const values = typeof response.headers.getSetCookie === "function"
    ? response.headers.getSetCookie()
    : [response.headers.get("set-cookie")].filter(Boolean);
  return values.map((value) => value.split(";")[0]).filter(Boolean);
}

function cookieHeader(cookies) {
  return cookies.join("; ");
}

function findCookie(cookies, name) {
  return cookies.find((cookie) => cookie.startsWith(`${name}=`));
}

const status = await fetch(`${baseUrl}/api/oidc/status`, { cache: "no-store" });
const statusPayload = await status.json();
assert(status.status === 200 && statusPayload.enabled === true, "OIDC status is not enabled in CI runtime");
process.stdout.write("ok OIDC runtime status enabled\n");

const login = await fetch(`${baseUrl}/api/oidc/login?return_to=%2Foverview`, {
  cache: "no-store",
  redirect: "manual",
});
assert(login.status >= 300 && login.status < 400, `OIDC login returned ${login.status}`);
const authorizeUrl = login.headers.get("location");
assert(authorizeUrl?.includes("/authorize"), "OIDC login did not redirect to authorization endpoint");
const transactionCookies = cookiesFrom(login);
assert(findCookie(transactionCookies, "__Host-tm_oidc_state"), "OIDC state cookie missing");
assert(findCookie(transactionCookies, "__Host-tm_oidc_verifier"), "OIDC verifier cookie missing");
assert(findCookie(transactionCookies, "__Host-tm_oidc_return"), "OIDC return cookie missing");
process.stdout.write("ok OIDC PKCE transaction established\n");

const authorize = await fetch(authorizeUrl, { redirect: "manual" });
assert(authorize.status >= 300 && authorize.status < 400, `mock authorization returned ${authorize.status}`);
const callbackUrl = authorize.headers.get("location");
assert(callbackUrl?.startsWith(`${baseUrl}/api/oidc/callback`), `unexpected callback URI: ${callbackUrl}`);
process.stdout.write("ok OIDC authorization redirect\n");

const callback = await fetch(callbackUrl, {
  headers: { cookie: cookieHeader(transactionCookies) },
  cache: "no-store",
  redirect: "manual",
});
assert(callback.status >= 300 && callback.status < 400, `OIDC callback returned ${callback.status}`);
const finalLocation = callback.headers.get("location") ?? "";
assert(finalLocation === `${baseUrl}/overview`, `OIDC callback returned to unexpected location: ${finalLocation}`);
const callbackCookies = cookiesFrom(callback);
const sessionCookie = findCookie(callbackCookies, "__Host-tm_session");
assert(sessionCookie?.includes("tm_test_admin"), "OIDC callback did not establish secure TractusMind session");
assert(callbackCookies.some((cookie) => cookie.startsWith("__Host-tm_oidc_state=")), "OIDC callback did not clear transaction state");
process.stdout.write("ok OIDC code exchange established session\n");

const session = await fetch(`${baseUrl}/api/session`, {
  headers: { cookie: sessionCookie },
  cache: "no-store",
});
const identity = await session.json();
assert(session.status === 200, `OIDC session validation returned ${session.status}`);
assert(identity.role === "admin" && identity.display_name === "CI Admin", "OIDC access token was not validated by backend identity route");
process.stdout.write("ok OIDC session validated through backend /v1/me\n");

const badLogin = await fetch(`${baseUrl}/api/oidc/login`, { redirect: "manual", cache: "no-store" });
const badCookies = cookiesFrom(badLogin);
const badCallback = await fetch(`${baseUrl}/api/oidc/callback?code=forged&state=forged`, {
  headers: { cookie: cookieHeader(badCookies) },
  redirect: "manual",
  cache: "no-store",
});
assert(badCallback.status >= 300 && badCallback.status < 400, `bad-state callback returned ${badCallback.status}`);
assert((badCallback.headers.get("location") ?? "").includes("auth_error=invalid_sso_state"), "bad OIDC state was not rejected");
process.stdout.write("ok OIDC state mismatch rejected\n");

const unsafeReturn = await fetch(`${baseUrl}/api/oidc/login?return_to=https%3A%2F%2Fevil.example`, { redirect: "manual", cache: "no-store" });
const unsafeCookies = cookiesFrom(unsafeReturn);
const returnCookie = findCookie(unsafeCookies, "__Host-tm_oidc_return") ?? "";
assert(returnCookie.endsWith("=/"), `unsafe return target was not normalized: ${returnCookie}`);
process.stdout.write("ok OIDC open-redirect target rejected\n");

process.stdout.write("Mission Control OIDC PKCE smoke passed.\n");
