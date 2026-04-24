/**
 * k6 load test — HostingGuard API
 *
 * Auth: cookie-based JWT (access_token + refresh_token).
 * k6 handles cookies automatically per VU via the default cookie jar.
 *
 * Usage:
 *   # Smoke (1 VU, 30s) — sanity check before real load
 *   k6 run -e BASE_URL=https://api.hostingguard.lat \
 *           -e TEST_EMAIL=your@email.com \
 *           -e TEST_PASSWORD=yourpassword \
 *           --scenario smoke tests/k6/load_test.js
 *
 *   # Load (10 VUs, 2min ramp + 3min steady)
 *   k6 run -e BASE_URL=https://api.hostingguard.lat \
 *           -e TEST_EMAIL=your@email.com \
 *           -e TEST_PASSWORD=yourpassword \
 *           tests/k6/load_test.js
 *
 * Thresholds (SLOs):
 *   - p95 response time < 800ms
 *   - error rate < 1%
 *   - login p99 < 1500ms
 */

import http from "k6/http";
import { check, group, sleep } from "k6";
import { Rate, Trend } from "k6/metrics";

// ---------------------------------------------------------------------------
// Custom metrics
// ---------------------------------------------------------------------------
const errorRate = new Rate("errors");
const loginDuration = new Trend("login_duration", true);
const hostingListDuration = new Trend("hosting_list_duration", true);

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------
const BASE_URL = __ENV.BASE_URL || "https://api.hostingguard.lat";
const EMAIL = __ENV.TEST_EMAIL || "test@hostingguard.lat";
const PASSWORD = __ENV.TEST_PASSWORD || "changeme";

// ---------------------------------------------------------------------------
// Scenarios
// ---------------------------------------------------------------------------
// Select scenario with: -e SCENARIO=smoke  (default: load)
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
    // Global p95 < 800ms
    http_req_duration: ["p(95)<800"],
    // Error rate < 1%
    errors: ["rate<0.01"],
    // Login specifically: p99 < 1500ms
    login_duration: ["p(99)<1500"],
    // Hosting list: p95 < 600ms
    hosting_list_duration: ["p(95)<600"],
  },
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
const JSON_HEADERS = { "Content-Type": "application/json" };

function assertOk(res, name) {
  const ok = check(res, {
    [`${name} status 2xx`]: (r) => r.status >= 200 && r.status < 300,
  });
  errorRate.add(!ok);
  return ok;
}

// ---------------------------------------------------------------------------
// Main VU loop
// ---------------------------------------------------------------------------
export default function () {
  // Each VU gets its own cookie jar automatically — simulates a real browser session.

  // ------------------------------------------------------------------
  // 1. Public health checks (no auth required)
  // ------------------------------------------------------------------
  group("health", () => {
    const live = http.get(`${BASE_URL}/health/live`);
    check(live, { "live 200": (r) => r.status === 200 });
    errorRate.add(live.status !== 200);

    const ready = http.get(`${BASE_URL}/health/ready`);
    check(ready, {
      "ready 200": (r) => r.status === 200,
      "ready postgres ok": (r) => {
        try {
          return JSON.parse(r.body).checks.postgres === "ok";
        } catch {
          return false;
        }
      },
    });
    errorRate.add(ready.status !== 200);
  });

  sleep(0.5);

  // ------------------------------------------------------------------
  // 2. Login
  // ------------------------------------------------------------------
  let loggedIn = false;
  group("auth", () => {
    const start = Date.now();
    const res = http.post(
      `${BASE_URL}/login`,
      JSON.stringify({ email: EMAIL, password: PASSWORD }),
      { headers: JSON_HEADERS }
    );
    loginDuration.add(Date.now() - start);

    loggedIn = assertOk(res, "login");
    if (!loggedIn) return;

    check(res, {
      "login has access_token cookie": (r) =>
        r.cookies["access_token"] !== undefined,
    });
  });

  if (!loggedIn) {
    sleep(1);
    return;
  }

  sleep(0.3);

  // ------------------------------------------------------------------
  // 3. /me — identity check
  // ------------------------------------------------------------------
  group("me", () => {
    const res = http.get(`${BASE_URL}/me`);
    const ok = assertOk(res, "me");
    if (ok) {
      check(res, {
        "me has user_id": (r) => {
          try {
            return JSON.parse(r.body).user_id !== undefined;
          } catch {
            return false;
          }
        },
      });
    }
  });

  sleep(0.3);

  // ------------------------------------------------------------------
  // 4. List hostings
  // ------------------------------------------------------------------
  group("hosting_list", () => {
    const start = Date.now();
    const res = http.get(`${BASE_URL}/list-hostings?skip=0&limit=20`);
    hostingListDuration.add(Date.now() - start);
    assertOk(res, "hosting_list");
  });

  sleep(0.5);

  // ------------------------------------------------------------------
  // 5. Logout — clean session
  // ------------------------------------------------------------------
  group("logout", () => {
    const res = http.post(`${BASE_URL}/logout`, null, {
      headers: JSON_HEADERS,
    });
    assertOk(res, "logout");
  });

  sleep(1);
}
