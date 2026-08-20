const baseUrl = (process.env.SMOKE_BASE_URL ?? "http://127.0.0.1:3100").replace(/\/$/, "");
const routes = ["/", "/overview", "/sources", "/ops", "/quality", "/admin"];

async function waitForServer() {
  let lastError;
  for (let attempt = 0; attempt < 40; attempt += 1) {
    try {
      const response = await fetch(`${baseUrl}/api/health`, { cache: "no-store" });
      if (response.ok) return;
      lastError = new Error(`health returned ${response.status}`);
    } catch (error) {
      lastError = error;
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw lastError ?? new Error("Mission Control did not become ready");
}

async function probeRoute(route) {
  const response = await fetch(`${baseUrl}${route}`, {
    cache: "no-store",
    redirect: "manual",
  });
  if (response.status !== 200) {
    throw new Error(`${route} returned ${response.status}`);
  }
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("text/html")) {
    throw new Error(`${route} returned unexpected content-type: ${contentType}`);
  }
  await response.arrayBuffer();
  process.stdout.write(`ok ${route}\n`);
}

await waitForServer();

const healthResponse = await fetch(`${baseUrl}/api/health`, { cache: "no-store" });
const health = await healthResponse.json();
if (!healthResponse.ok || health.status !== "ok") {
  throw new Error(`/api/health failed: ${healthResponse.status} ${JSON.stringify(health)}`);
}
process.stdout.write("ok /api/health\n");

for (const route of routes) {
  await probeRoute(route);
}

process.stdout.write(`Mission Control smoke passed (${routes.length + 1} routes).\n`);
