"""Email dispatch via Resend for KırCan Report AI."""
import os
import asyncio
import base64
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any

import resend

logger = logging.getLogger(__name__)

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "onboarding@resend.dev")
SENDER_NAME = "KırCan Report AI"

if RESEND_API_KEY:
    resend.api_key = RESEND_API_KEY


def _wrap_brand(inner_html: str, preheader: str = "") -> str:
    """Wrap content in a branded KırCan template (navy + gold, inline CSS, table layout)."""
    return f"""\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8" /></head>
<body style="margin:0;padding:0;background-color:#f4f4f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;">
  <span style="display:none;visibility:hidden;opacity:0;height:0;width:0;font-size:1px;line-height:1px;color:#f4f4f5;">{preheader}</span>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#f4f4f5;padding:32px 16px;">
    <tr><td align="center">
      <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;background-color:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(11,35,64,0.08);">
        <tr>
          <td style="background:linear-gradient(135deg,#081a30 0%,#0b2340 45%,#0e2a4d 100%);padding:32px 32px 28px 32px;">
            <div style="font-family:'Courier New',monospace;font-size:11px;letter-spacing:0.28em;color:#d4af37;text-transform:uppercase;margin-bottom:6px;">KırCan Report AI</div>
            <div style="font-size:22px;color:#ffffff;font-weight:300;letter-spacing:-0.5px;">Gayrimenkul Değerleme Asistanı</div>
          </td>
        </tr>
        <tr>
          <td style="padding:32px 32px 24px 32px;color:#1a1a1a;font-size:15px;line-height:1.6;">
            {inner_html}
          </td>
        </tr>
        <tr>
          <td style="padding:20px 32px;background-color:#fafafa;border-top:1px solid #e5e5e5;text-align:center;">
            <div style="font-family:'Courier New',monospace;font-size:10px;letter-spacing:0.25em;color:#9ca3af;text-transform:uppercase;">
              Powered by <span style="color:#c9a24a;font-weight:600;">Algorisma</span>
            </div>
          </td>
        </tr>
      </table>
      <div style="max-width:600px;color:#9ca3af;font-size:11px;padding:16px 8px;text-align:center;">
        KırCan Danışmanlık, Eğitim ve Değerleme Ltd. Şti.
      </div>
    </td></tr>
  </table>
</body>
</html>
"""


async def send_email(
    to: str,
    subject: str,
    html: str,
    attachments: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Send an email via Resend (non-blocking via to_thread).

    attachments: list of {"path": str, "filename": str} — read from disk, base64-encoded.
    Returns Resend response ({"id": ...}) or raises RuntimeError on failure.
    """
    if not RESEND_API_KEY:
        raise RuntimeError("RESEND_API_KEY not configured")

    params: Dict[str, Any] = {
        "from": f"{SENDER_NAME} <{SENDER_EMAIL}>",
        "to": [to],
        "subject": subject,
        "html": html,
    }

    if attachments:
        payload_atts = []
        for att in attachments:
            path = Path(att["path"])
            if not path.exists():
                logger.warning(f"Attachment missing: {path}")
                continue
            data = path.read_bytes()
            payload_atts.append({
                "filename": att.get("filename", path.name),
                "content": base64.b64encode(data).decode("ascii"),
            })
        if payload_atts:
            params["attachments"] = payload_atts

    try:
        result = await asyncio.to_thread(resend.Emails.send, params)
        logger.info(f"Resend sent id={result.get('id')} to={to}")
        return result
    except Exception as e:
        logger.exception(f"Resend send failed to={to}")
        raise RuntimeError(str(e))


def report_ready_email(user_name: str, template_name: str, report_no: str) -> str:
    """HTML body for 'your report is ready' with the DOCX attached."""
    inner = f"""
      <div style="font-size:12px;letter-spacing:0.25em;color:#c9a24a;text-transform:uppercase;margin-bottom:8px;">Raporunuz Hazır</div>
      <h1 style="margin:0 0 16px 0;font-size:24px;color:#0b2340;font-weight:600;">Merhaba {user_name},</h1>
      <p style="margin:0 0 12px 0;">
        <b>{template_name}</b> raporunuz başarıyla tamamlandı ve bu e-postaya <b>Word (.docx)</b> formatında eklendi.
      </p>
      <table role="presentation" cellpadding="0" cellspacing="0" style="margin:20px 0;background-color:#f8f9fa;border-left:3px solid #d4af37;padding:16px 20px;">
        <tr><td>
          <div style="font-family:'Courier New',monospace;font-size:10px;letter-spacing:0.25em;color:#6b7280;text-transform:uppercase;margin-bottom:4px;">Rapor No</div>
          <div style="font-size:18px;color:#0b2340;font-weight:600;">{report_no}</div>
        </td></tr>
      </table>
      <p style="margin:12px 0 0 0;color:#4b5563;font-size:14px;">
        Ekteki dosyayı istediğiniz zaman KırCan Report AI panelinizden de tekrar indirebilirsiniz. Bu rapor hakkında herhangi bir sorunuz olursa bu e-postayı yanıtlamanız yeterlidir.
      </p>
    """
    return _wrap_brand(inner, preheader=f"{template_name} raporunuz ekte")


def invite_email(inviter_email: str, company_name: Optional[str], role: str, join_url: str) -> str:
    """HTML body for invite link email."""
    role_label = "yönetici" if role == "admin" else "kullanıcı"
    company_line = f"<b>{company_name}</b> şirketine " if company_name else ""
    inner = f"""
      <div style="font-size:12px;letter-spacing:0.25em;color:#c9a24a;text-transform:uppercase;margin-bottom:8px;">Davetiye</div>
      <h1 style="margin:0 0 16px 0;font-size:24px;color:#0b2340;font-weight:600;">KırCan Report AI'a davetlisiniz</h1>
      <p style="margin:0 0 20px 0;">
        <b>{inviter_email}</b> sizi {company_line}{role_label} olarak <b>KırCan Report AI</b>'a davet etti.
      </p>
      <table role="presentation" cellpadding="0" cellspacing="0" style="margin:24px 0;">
        <tr><td>
          <a href="{join_url}" style="display:inline-block;background-color:#0b2340;color:#ffffff;padding:14px 28px;text-decoration:none;border-radius:6px;font-weight:600;font-size:15px;">
            Daveti Kabul Et →
          </a>
        </td></tr>
      </table>
      <p style="margin:20px 0 0 0;color:#6b7280;font-size:13px;">
        Bağlantı çalışmıyorsa aşağıdaki adresi tarayıcınıza kopyalayın:<br />
        <span style="font-family:'Courier New',monospace;font-size:12px;word-break:break-all;color:#0b2340;">{join_url}</span>
      </p>
      <p style="margin:16px 0 0 0;color:#9ca3af;font-size:12px;">
        Bu daveti beklemiyorsanız, bu e-postayı yok sayabilirsiniz.
      </p>
    """
    return _wrap_brand(inner, preheader=f"KırCan Report AI davetiniz — {role_label}")
