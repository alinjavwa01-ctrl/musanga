"""Outbound email for quotes and signature invites.

Two backends, tried in that order:

  1. Resend         — a real transactional provider. Set RESEND_API_KEY and
                      the cap on how many messages leave per hour becomes the
                      Resend plan, not two. This is what production wants.
  2. Supabase Auth  — the magic-link mailer that lives inside the Supabase
                      project. No new keys, but 2 mails/hour on free tier and
                      the from-address is Supabase's. Kept as a fallback so
                      the platform still sends when Resend is not configured.

The rendered HTML is the same either way, so a quote a customer opens by
clicking a Resend email is indistinguishable from one opened via Supabase.
The caller does not know which path went out; the (ok, note) tuple names the
one that did in the note.
"""

import json
import os
import urllib.error
import urllib.request


# --- Resend ---------------------------------------------------------------

RESEND_KEY_ENV = "RESEND_API_KEY"
RESEND_FROM_ENV = "RESEND_FROM"
DEFAULT_RESEND_FROM = "Musanga <quotes@musanga.dev>"


def resend_configured():
    return bool(os.environ.get(RESEND_KEY_ENV))


def _resend_send(email, subject, html):
    key = os.environ.get(RESEND_KEY_ENV)
    if not key:
        return False, "resend not configured"
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=json.dumps({
            "from": os.environ.get(RESEND_FROM_ENV) or DEFAULT_RESEND_FROM,
            "to": [email.strip()],
            "subject": subject,
            "html": html,
        }).encode(),
        headers={
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            resp.read()
            return True, "sent via Resend"
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", "replace")[:200]
        except Exception:  # noqa: BLE001
            body = ""
        return False, "Resend %d: %s" % (e.code, body)
    except Exception as e:  # noqa: BLE001
        return False, "network: %s" % (str(e)[:120])


# --- Supabase Auth (fallback) ---------------------------------------------

SUPABASE_URL_ENV = "SUPABASE_URL"
SUPABASE_KEY_ENV = "SUPABASE_ANON_KEY"

# The publishable / anon key is public by design - it is what every browser
# bundle carries. Pinning it here means Vercel needs nothing set for the
# fallback mailer to work; the env vars are still honoured for local override.
DEFAULT_SUPABASE_URL = "https://xfpwiygsiojbasvbcdon.supabase.co"
DEFAULT_SUPABASE_ANON_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InhmcHdpeWdzaW9qYmFzdmJjZG9uIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODc5MTMwMTksImV4cCI6MjEwMzQ4OTAxOX0."
    "iQr0iYbg-l-Db-rzZLTefqK3YlLuL3TMZ8SZ_9j6QaU"
)


def _supabase_url():
    return os.environ.get(SUPABASE_URL_ENV) or DEFAULT_SUPABASE_URL


def _supabase_key():
    return os.environ.get(SUPABASE_KEY_ENV) or DEFAULT_SUPABASE_ANON_KEY


def supabase_configured():
    return bool(_supabase_url() and _supabase_key())


def _supabase_otp(email, redirect_url, data):
    """Ask Supabase Auth to email a magic link that redirects to `redirect_url`."""
    if not supabase_configured():
        return False, "Supabase mailer is not configured"
    url = _supabase_url().rstrip("/") + "/auth/v1/otp"
    key = _supabase_key()
    payload = {
        "email": email.strip(),
        "create_user": True,
        "options": {"email_redirect_to": redirect_url, "data": data},
    }
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "apikey": key,
            "Authorization": "Bearer " + key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            resp.read()
            return True, "sent via Supabase Auth"
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", "replace")[:200]
        except Exception:  # noqa: BLE001
            body = ""
        return False, "Supabase %d: %s" % (e.code, body)
    except Exception as e:  # noqa: BLE001
        return False, "network: %s" % (str(e)[:120])


# Kept for pre-existing callers that consult `mailer.configured()`.
def configured():
    return resend_configured() or supabase_configured()


# --- HTML rendering -------------------------------------------------------

def _quote_html(url, ref, counterparty, corridor, total, reminder=False, doc=False):
    headline = "A reminder about your rate" if reminder else "Your rate is ready to sign"
    subline = "%s — <b>%s</b>, all in. Review and sign the rate. Musanga will confirm and schedule the truck." % (
        _esc(corridor), _esc(total))
    doc_note = ("<p style=\"margin:0;font-size:13px;color:#667085;line-height:1.55\">"
                "A signed document is attached to the rate for your review."
                "</p>") if doc else ""
    return _EMAIL_TEMPLATE.format(
        kicker="Musanga rate · " + _esc(ref),
        headline=_esc(headline),
        subline=subline,
        cta_url=_esc(url),
        counterparty=_esc(counterparty),
        doc_note=doc_note,
    )


def _agreement_html(url, ref, title, counterparty, reminder=False):
    headline = "A reminder about your document" if reminder else "A document is ready to sign"
    subline = "%s for %s. Review and sign in one place." % (_esc(title), _esc(counterparty))
    return _EMAIL_TEMPLATE.format(
        kicker="Musanga contract · " + _esc(ref),
        headline=_esc(headline),
        subline=subline,
        cta_url=_esc(url),
        counterparty=_esc(counterparty),
        doc_note="",
    )


def _esc(s):
    return (str(s) if s is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


_EMAIL_TEMPLATE = """<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f5f7;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;padding:32px 0">
  <tr><td align="center">
    <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="width:600px;max-width:100%;background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 12px 40px rgba(16,24,40,.08)">
      <tr><td style="padding:32px 40px 0">
        <div style="font-size:14px;color:#101828;font-weight:700;letter-spacing:-.01em">Musanga</div>
      </td></tr>
      <tr><td>
        <img src="https://musanga.vercel.app/img/quote-hero.jpg" alt="" width="600" style="display:block;width:100%;height:auto;margin-top:24px">
      </td></tr>
      <tr><td style="padding:36px 40px 16px">
        <div style="font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:#667085;margin-bottom:10px">{kicker}</div>
        <h1 style="margin:0;font-size:32px;line-height:1.15;color:#101828;letter-spacing:-.02em">{headline}</h1>
        <p style="margin:14px 0 0;font-size:16px;line-height:1.5;color:#475467">{subline}</p>
      </td></tr>
      <tr><td style="padding:28px 40px 8px" align="left">
        <a href="{cta_url}" style="display:inline-block;background:#1a73e8;color:#ffffff;text-decoration:none;padding:16px 30px;border-radius:10px;font-size:16px;font-weight:600;letter-spacing:.1px">Review &amp; sign</a>
      </td></tr>
      <tr><td style="padding:22px 40px 36px">
        {doc_note}
        <p style="margin:8px 0 0;font-size:13px;color:#98a2b3;line-height:1.55">
          The link opens the private page for {counterparty}. If you were not expecting this,
          reply and let us know — nothing on your account changes until you sign.
        </p>
      </td></tr>
    </table>
    <div style="max-width:600px;margin:16px auto 0;padding:0 8px;text-align:center;font-size:12px;color:#98a2b3">
      Musanga Logistics · Ten years moving Zambia · <a href="https://musanga.vercel.app" style="color:#667085">musanga.vercel.app</a>
    </div>
  </td></tr>
</table>"""


# --- what the rest of the platform calls ----------------------------------

def send_sign_invite(email, sign_url, agreement):
    if not email or not email.strip():
        return False, "no counterparty email"
    ref = agreement.get("ref") or ""
    title = agreement.get("title") or "Musanga contract"
    counterparty = agreement.get("counterparty") or ""
    if resend_configured():
        html = _agreement_html(sign_url, ref, title, counterparty)
        return _resend_send(email, "Musanga: sign %s — %s" % (ref, title), html)
    return _supabase_otp(email, sign_url, {
        "agreement_ref": ref, "agreement_title": title, "counterparty": counterparty,
    })


def send_quote_invite(email, quote_url, quote):
    """Email a rate to a customer. Prefers Resend when RESEND_API_KEY is set;
    otherwise falls back to Supabase Auth's magic-link mailer."""
    if not email or not email.strip():
        return False, "no counterparty email"
    ref = quote.get("ref") or ""
    corridor = quote.get("corridor") or ""
    total = quote.get("total") or ""
    counterparty = quote.get("counterparty") or ""
    reminder = bool(quote.get("reminder"))
    doc = bool(quote.get("has_document"))
    if resend_configured():
        html = _quote_html(quote_url, ref, counterparty, corridor, total,
                           reminder=reminder, doc=doc)
        subject = ("Reminder: your Musanga rate " if reminder else "Your Musanga rate ") + ref
        return _resend_send(email, subject, html)
    return _supabase_otp(email, quote_url, {
        "quote_ref": ref, "quote_title": quote.get("title"),
        "counterparty": counterparty, "corridor": corridor, "total": total,
        "reminder": reminder,
    })
