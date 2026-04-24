/**
 * k6 load test — HostingGuard API
 *
 * Auth: cookie-based JWT. Login happens once in setup() and the
 * access_token cookie is injected per-VU to avoid hitting the
 * rate limit on /login (5/minute).
 *
 * Usage:
 *   # Smoke (1 VU, 30s)
 *   k6 run -e BASE_URL=https://api.hostingguard.lat \
 *           -e TEST_EMAIL=k6test@hostingguard.lat \
 *           -e TEST_PASSWORD=K6LoadTest2026! \
 *           -e SCENARIO=smoke \
 *           tests/k6/load_test.js
 *
 *   # Load (10 VUs, ramp 1m + steady 3m)
 *   k6 run -e BASE_URL=https://api.hostingguard.lat \
 *           -e TEST_EMAIL=k6test@hostingguard.lat \
 *           -e TEST_PASSWORD=K6LoadTest2026! \
 *           tests/k6/load_test.js
 *
 * Thresholds (SLOs):
 *   - p95 response time < 800ms
 *   - error rate < 1%
 *   - hosting list p95 < 600ms
 */

import http from "k6/http";
import { check, group, sleep } from "k6";
import { Rate, Trend } from "k6/metrics";

// ---------------------------------------------------------------------------
// Custom metrics
// ---------------------------------------------------------------------------
const errorRate = new Rate("errors");
const hostingListDuration = new Trend("hosting_list_duration", true);
const meDuration = new Trend("me_duration", true);

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------
const BASE_URL = __ENV.BASE_URL || "https://api.hostingguard.lat";
const EMAIL = __ENV.TEST_EMAIL || "k6test@hostingguard.lat";
const PASSWORD = __ENV.TEST_PASSWORD || "K6LoadTest2026!";
const SCENARIO = __ENV.SCENARIO || "load";

const SCENARIOS = {
  smoke: {
    executor: "constant-vus",
    vus: 1,
    duration: "30s",
    tags: { scenario: "smoke" },
  },
  load: {
    executor: "ramping-vus",
    startVUs: 0,
    stages: [
      { duration: "1m", target: 10 },
      { duration: "3m", target: 10 },
      { duration: "30s", target: 0 },
    ],
    tags: { scenario: "load" },
  },
};

export const options = {
  scenarios: { [SCENARIO]: SCENARIOS[SCENARIO] },
  thresholds: {
    http_req_duration: ["p(95)<800"],
    errors: ["rate<0.01"],
    hosting_list_duration: ["p(95)<600"],
    me_duration: ["p(95)<400"],
  },
};

// ---------------------------------------------------------------------------
// setup() — runs once before all VUs start.
// Logs in and returns the access_token cookie value.
// ---------------------------------------------------------------------------
export function setup() {
  const res = http.post(
    `${BASE_URL}/login`,
    JSON.stringify({ email: EMAIL, password: PASSWORD }),
    { headers: { "Content-Type": "application/json" } }
  );

  if (res.status !== 200) {
    throw new Error(
      `setup(): login failed — status=${res.status} body=${res.body}`
    );
  }

  const cookie = res.cookies["access_token"];
  if (!cookie || !cookie[0]) {
    throw new Error("setup(): access_token cookie not found in login response");
  }

  return { accessToken: cookie[0].value };
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function authHeaders(token) {
  return {
    headers: { "Content-Type": "application/json" },
    cookies: { access_token: token },
  };
}

function assertOk(res, name) {
  const ok = check(res, {
    [`${name} status 2xx`]: (r) => r.status >= 200 && r.status < 300,
  });
  errorRate.add(!ok);
  return ok;
}

// ---------------------------------------------------------------------------
// Main VU loop — data.accessToken injected from setup()
// ---------------------------------------------------------------------------
export default function (data) {
  const token = data.accessToken;

  // ------------------------------------------------------------------
  // 1. Public health checks
  // ------------------------------------------------------------------
  group("health", () => {
    const live = http.get(`${BASE_URL}/health/live`);
    check(live, { "live 200": (r) => r.status === 200 });
    errorRate.add(live.status !== 200);

    const ready = http.get(`${BASE_URL}/health/ready`);
    check(ready, {
      "ready 200": (r) => r.status === 200,
      "ready postgres ok": (r) => {
        try { return JSON.parse(r.body).checks.postgres === "ok"; }
        catch { return false; }
      },
    });
    errorRate.add(ready.status !== 200);
  });

  sleep(0.2);

  // ------------------------------------------------------------------
  // 2. /me — identity + auth validation
  // ------------------------------------------------------------------
  group("me", () => {
    const start = Date.now();
    const res = http.get(`${BASE_URL}/me`, authHeaders(token));
    meDuration.add(Date.now() - start);

    const ok = assertOk(res, "me");
    if (ok) {
      check(res, {
        "me has user_id": (r) => {
          try { return JSON.parse(r.body).user_id !== undefined; }
          catch { return false; }
        },
      });
    }
  });

  sleep(0.2);

  // ------------------------------------------------------------------
  // 3. List hostings
  // ------------------------------------------------------------------
  group("hosting_list", () => {
    const start = Date.now();
    const res = http.get(
      `${BASE_URL}/list-hostings?skip=0&limit=20`,
      authHeaders(token)
    );
    hostingListDuration.add(Date.now() - start);
    assertOk(res, "hosting_list");
  });

  sleep(0.5);
}
