"""
Mailer — transactional emails for HostingGuard.

Config (env vars):
  SMTP_HOST     e.g. smtp.gmail.com or smtp.sendgrid.net
  SMTP_PORT     default 587 (STARTTLS)
  SMTP_USER     sender username / API key login
  SMTP_PASS     password or API key
  FROM_EMAIL    e.g. noreply@hostingguard.lat
  APP_URL       e.g. https://hostingguard.lat (used to build links)

If SMTP_HOST is not set the link is logged at WARNING level so development
works without email infrastructure.
"""
import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


def _cfg():
    return {
        "host":       os.getenv("SMTP_HOST", ""),
        "port":       int(os.getenv("SMTP_PORT", "587")),
        "user":       os.getenv("SMTP_USER", ""),
        "password":   os.getenv("SMTP_PASS", ""),
        "from_email": os.getenv("FROM_EMAIL", "noreply@hostingguard.lat"),
        "app_url":    os.getenv("APP_URL", "https://hostingguard.lat").rstrip("/"),
    }


def _send(to_email: str, subject: str, html: str, text: str) -> None:
    c = _cfg()
    if not c["host"]:
        logger.warning("[mailer] SMTP_HOST not configured — skipping real send.\nTo: %s\nSubject: %s\nHTML preview: %s…", to_email, subject, html[:200])
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"HostingGuard <{c['from_email']}>"
    msg["To"]      = to_email
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html",  "utf-8"))

    try:
        with smtplib.SMTP(c["host"], c["port"], timeout=10) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(c["user"], c["password"])
            smtp.sendmail(c["from_email"], [to_email], msg.as_bytes())
        logger.info("[mailer] Sent '%s' to %s", subject, to_email)
    except Exception as exc:
        logger.error("[mailer] Failed to send '%s' to %s: %s", subject, to_email, exc)
        raise


# ── HTML shell ────────────────────────────────────────────────────────────────

def _html_wrap(title: str, body: str, app_url: str = "") -> str:
    app_url = app_url or _cfg()["app_url"]
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{title}</title>
</head>
<body style="margin:0;padding:0;background:#080809;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#080809;padding:40px 16px;">
    <tr>
      <td align="center">
        <table width="100%" style="max-width:520px;background:#111;border:1px solid rgba(255,255,255,0.08);border-radius:16px;overflow:hidden;">
          <!-- Header -->
          <tr>
            <td style="padding:28px 32px 20px;border-bottom:1px solid rgba(255,255,255,0.06);">
              <span style="font-size:20px;font-weight:800;color:#fff;">Hosting<span style="color:#00ff88;">Guard</span></span>
            </td>
          </tr>
          <!-- Body -->
          <tr>
            <td style="padding:32px;">
              {body}
            </td>
          </tr>
          <!-- Footer -->
          <tr>
            <td style="padding:20px 32px;border-top:1px solid rgba(255,255,255,0.06);text-align:center;">
              <p style="margin:0;font-size:11px;color:#555;">
                © 2026 HostingGuard · <a href="{app_url}/privacy" style="color:#555;">Privacidad</a> · <a href="{app_url}/terminos" style="color:#555;">Términos</a>
              </p>
              <p style="margin:6px 0 0;font-size:11px;color:#444;">
                Si no realizaste esta acción, podés ignorar este correo.
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _btn(href: str, label: str) -> str:
    return (
        f'<a href="{href}" style="display:inline-block;background:#00ff88;color:#000;'
        f'font-weight:800;font-size:14px;padding:14px 32px;border-radius:10px;'
        f'text-decoration:none;letter-spacing:.5px;">{label}</a>'
    )


# ── Public API ────────────────────────────────────────────────────────────────

def send_verification_email(to_email: str, first_name: str, token: str) -> None:
    app_url = _cfg()["app_url"]
    link = f"{app_url}/verify-email?token={token}"
    subject = "Verificá tu email — HostingGuard"

    body_html = f"""
      <h2 style="margin:0 0 8px;font-size:22px;font-weight:800;color:#fff;">¡Hola, {first_name}!</h2>
      <p style="margin:0 0 24px;font-size:15px;color:#aaa;line-height:1.6;">
        Gracias por registrarte en HostingGuard. Para activar tu cuenta y comenzar a crear proyectos,
        verificá tu dirección de email haciendo clic en el botón de abajo.
      </p>
      <p style="margin:0 0 32px;text-align:center;">{_btn(link, 'VERIFICAR MI EMAIL')}</p>
      <p style="margin:0 0 8px;font-size:12px;color:#555;">O copiá este enlace en tu navegador:</p>
      <p style="margin:0;font-size:11px;color:#555;word-break:break-all;">{link}</p>
      <hr style="margin:28px 0;border:none;border-top:1px solid rgba(255,255,255,0.06);" />
      <p style="margin:0;font-size:12px;color:#555;">
        Este enlace expira en <strong style="color:#aaa;">24 horas</strong>.
        Si no creaste una cuenta en HostingGuard, podés ignorar este correo.
      </p>
    """
    body_text = (
        f"Hola {first_name},\n\n"
        f"Verificá tu email haciendo clic en el siguiente enlace (válido 24 h):\n{link}\n\n"
        f"Si no creaste una cuenta, ignorá este correo.\n\nHostingGuard"
    )
    _send(to_email, subject, _html_wrap(subject, body_html, app_url), body_text)


def send_password_reset_email(to_email: str, first_name: str, token: str) -> None:
    app_url = _cfg()["app_url"]
    link = f"{app_url}/reset-password?token={token}"
    subject = "Restablecer contraseña — HostingGuard"

    body_html = f"""
      <h2 style="margin:0 0 8px;font-size:22px;font-weight:800;color:#fff;">Restablecer contraseña</h2>
      <p style="margin:0 0 8px;font-size:15px;color:#aaa;">Hola, {first_name}.</p>
      <p style="margin:0 0 24px;font-size:15px;color:#aaa;line-height:1.6;">
        Recibimos una solicitud para restablecer la contraseña de tu cuenta.
        Si fuiste vos, hacé clic en el botón de abajo. Si no, podés ignorar este correo — tu contraseña no cambiará.
      </p>
      <p style="margin:0 0 32px;text-align:center;">{_btn(link, 'RESTABLECER CONTRASEÑA')}</p>
      <p style="margin:0 0 8px;font-size:12px;color:#555;">O copiá este enlace en tu navegador:</p>
      <p style="margin:0;font-size:11px;color:#555;word-break:break-all;">{link}</p>
      <hr style="margin:28px 0;border:none;border-top:1px solid rgba(255,255,255,0.06);" />
      <p style="margin:0;font-size:12px;color:#555;">
        Este enlace expira en <strong style="color:#aaa;">1 hora</strong> y solo puede usarse una vez.
      </p>
    """
    body_text = (
        f"Hola {first_name},\n\n"
        f"Para restablecer tu contraseña, ingresá al siguiente enlace (válido 1 h):\n{link}\n\n"
        f"Si no solicitaste esto, ignorá este correo.\n\nHostingGuard"
    )
    _send(to_email, subject, _html_wrap(subject, body_html, app_url), body_text)
