"""Sending an invite to sign.

The mailer runs against Supabase Auth: calling POST /auth/v1/otp with the
counterparty's email tells Supabase to send them a magic link, and the link
lands them on the agreement's sign URL. We do not use the auth session that
comes back from clicking it - the sign page already has its own token in the
URL - so this is Supabase's outbox and nothing else.

The catch, honestly stated: Supabase's built-in SMTP is capped at 2 mails an
hour on the free tier, and mails go out from noreply@mail.app.supabase.io.
For a real Musanga send-off, register a domain, plug an SMTP provider into
Supabase Auth Settings, and this file keeps working unchanged.
"""

import json
import os
import urllib.error
import urllib.request


SUPABASE_URL_ENV = "SUPABASE_URL"
SUPABASE_KEY_ENV = "SUPABASE_ANON_KEY"


def configured():
    return bool(os.environ.get(SUPABASE_URL_ENV) and os.environ.get(SUPABASE_KEY_ENV))


def send_sign_invite(email, sign_url, agreement):
    """Ask Supabase to email a magic link that redirects to the sign URL.

    Returns (ok, note). A failure never bubbles up as a 500 - a contract can
    be sent by copying the link, and the mailer being down should not stop
    ops from moving.
    """
    if not email or not email.strip():
        return False, "no counterparty email"
    if not configured():
        return False, "Supabase mailer is not configured"

    url = os.environ[SUPABASE_URL_ENV].rstrip("/") + "/auth/v1/otp"
    key = os.environ[SUPABASE_KEY_ENV]
    payload = {
        "email": email.strip(),
        "create_user": True,
        "options": {
            "email_redirect_to": sign_url,
            "data": {
                "agreement_ref": agreement.get("ref"),
                "agreement_title": agreement.get("title"),
                "counterparty": agreement.get("counterparty"),
            },
        },
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
