# Musanga email templates

Musanga sends transactional email through Supabase Auth. The magic-link
template lives in the Supabase dashboard, not this repository — Supabase renders
it. This directory keeps the HTML we want that template to be, so anyone can
diff, review or restore it without opening the dashboard.

## How to install

1. Supabase dashboard → Authentication → Email Templates → **Magic Link**.
2. Set the subject to `Your Musanga rate is ready — {{ .Data.quote_ref }}`.
3. Paste [`magic-link.html`](magic-link.html) into the message body.
4. Save. The next quote Ops sends uses the new template.

The template covers both flows the platform uses today — quotes (`quote_ref`,
`quote_title`, `corridor`, `total`) and signatures (`agreement_ref`,
`agreement_title`) — by falling back to whichever variables are present. One
template, two purposes, so ops does not have to keep two in sync.

## Reminder marker

`send_quote_invite(..., reminder=True)` sets a `reminder` flag in the
payload. The template reads `{{ if .Data.reminder }}` to swap the headline
from "Your rate is ready" to "A reminder about your rate", so a nudge does
not read like the first email.
