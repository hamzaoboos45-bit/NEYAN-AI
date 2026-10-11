"""
backend/email/templates.py — Email content for the auth flow.

Kept separate from email_service.py's send/provider logic so the *content*
of an email can change without touching how it's transmitted, and vice
versa. Only one email type exists today (password reset); if a second one
is ever needed, it gets its own build_*() function here, not a new module.

Bilingual by design: the `users` table has no stored language preference
(the app's EN/AR toggle is a client-side-only `localStorage` value, never
sent to the server), so per the brief's fallback instruction this uses the
existing default behavior of the auth flow's own server-generated text,
which is English — with an Arabic section included as well, since this is
an Arabic-first product and the recipient may prefer either.
"""

TOKEN_TTL_MINUTES = 30  # kept in sync with backend/security/password_reset.py


def build_password_reset_email(reset_link: str) -> dict:
    """Returns {"subject": str, "text": str, "html": str}."""
    subject = "Neyan AI — Password Reset Request / طلب إعادة تعيين كلمة المرور"

    text = f"""Neyan AI — Password Reset Request

We received a request to reset the password for your Neyan AI account.

Reset your password using the link below. This link is valid for
{TOKEN_TTL_MINUTES} minutes and can only be used once:

{reset_link}

If you did not request this, you can safely ignore this email — your
password will not be changed.

—

نيان AI — طلب إعادة تعيين كلمة المرور

وصلنا طلب لإعادة تعيين كلمة المرور لحسابك في نيان AI.

لإعادة تعيين كلمة المرور استخدم الرابط التالي. هذا الرابط صالح لمدة
{TOKEN_TTL_MINUTES} دقيقة ويمكن استخدامه مرة واحدة فقط:

{reset_link}

إذا لم تطلب هذا الإجراء، يمكنك تجاهل هذه الرسالة بأمان — لن يتم تغيير
كلمة المرور الخاصة بك.
"""

    html = f"""\
<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#08111F;font-family:Arial,Helvetica,sans-serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#08111F;padding:32px 16px;">
    <tr><td align="center">
      <table role="presentation" width="480" cellpadding="0" cellspacing="0" style="max-width:480px;background:#101A2B;border-radius:14px;border:1px solid rgba(255,255,255,.08);overflow:hidden;">
        <tr><td style="padding:28px 32px 8px;">
          <div style="font-size:15px;font-weight:700;letter-spacing:.08em;color:#F1DA84;">NEYAN <span style="color:#D4AF37;">AI</span></div>
        </td></tr>
        <tr><td style="padding:8px 32px 0;">
          <h1 style="font-size:19px;color:#FFFFFF;margin:12px 0 6px;">Password Reset Request</h1>
          <p style="font-size:14px;line-height:1.6;color:#B7BDC8;margin:0 0 20px;">
            We received a request to reset the password for your Neyan AI account.
            This link is valid for {TOKEN_TTL_MINUTES} minutes and can only be used once.
          </p>
        </td></tr>
        <tr><td style="padding:0 32px 24px;">
          <a href="{reset_link}" style="display:inline-block;background:linear-gradient(135deg,#F1DA84,#D4AF37 55%,#A67F1F);color:#16110A;text-decoration:none;font-weight:700;font-size:14px;padding:13px 26px;border-radius:999px;">Reset Password</a>
        </td></tr>
        <tr><td style="padding:0 32px 24px;">
          <p style="font-size:12px;line-height:1.6;color:#6b7280;margin:0;">
            If the button doesn't work, copy and paste this link into your browser:<br>
            <span style="color:#8b95a3;word-break:break-all;">{reset_link}</span>
          </p>
        </td></tr>
        <tr><td style="padding:0 32px 28px;border-top:1px solid rgba(255,255,255,.08);">
          <p style="font-size:12.5px;line-height:1.6;color:#8b95a3;margin:18px 0 0;">
            If you did not request this, you can safely ignore this email — your password will not be changed.
          </p>
        </td></tr>
        <tr><td dir="rtl" style="padding:20px 32px 28px;border-top:1px solid rgba(255,255,255,.08);text-align:right;">
          <h2 style="font-size:16px;color:#FFFFFF;margin:0 0 6px;">طلب إعادة تعيين كلمة المرور</h2>
          <p style="font-size:13.5px;line-height:1.8;color:#B7BDC8;margin:0 0 14px;">
            وصلنا طلب لإعادة تعيين كلمة المرور لحسابك في نيان AI. هذا الرابط صالح لمدة {TOKEN_TTL_MINUTES} دقيقة ويُستخدم مرة واحدة فقط.
          </p>
          <p style="font-size:12px;line-height:1.8;color:#8b95a3;margin:0;">
            إذا لم تطلب هذا الإجراء، تجاهل هذه الرسالة — لن تتغيّر كلمة المرور الخاصة بك.
          </p>
        </td></tr>
      </table>
      <p style="font-size:11px;color:#4b5563;margin-top:18px;">© Neyan AI — Transport Platform</p>
    </td></tr>
  </table>
</body>
</html>
"""
    return {"subject": subject, "text": text, "html": html}
