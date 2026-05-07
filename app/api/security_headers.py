from starlette.middleware.base import BaseHTTPMiddleware

# Paths that skip security headers (health probes hit these at high frequency)
_SKIP_PATHS = frozenset({"/health", "/health/live", "/health/ready"})


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.url.path in _SKIP_PATHS:
            return await call_next(request)

        response = await call_next(request)

        # Replace the default "uvicorn" Server header to avoid fingerprinting
        response.headers["Server"] = "hostingguard"

        # Prevent MIME-type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Deny framing (clickjacking protection)
        response.headers["X-Frame-Options"] = "DENY"

        # Do not send Referer header on cross-origin requests
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Force HTTPS for 1 year, include all subdomains
        # Only effective over HTTPS — safe to send always since Traefik enforces TLS
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains; preload"
        )

        # Disable browser features not used by this API
        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=(), payment=(), usb=()"
        )

        # Content Security Policy — API responses are JSON, not HTML.
        # This prevents browsers from rendering error responses as executable content.
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; frame-ancestors 'none'"
        )

        # Legacy XSS filter (IE/old Chrome) — belt-and-suspenders
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Prevent browsers from caching auth responses
        if request.url.path in ("/login", "/refresh", "/me", "/logout"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
            response.headers["Pragma"] = "no-cache"

        return response
