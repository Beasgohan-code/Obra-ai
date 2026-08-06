"""Optional Gmail + Google Calendar tools (require OAuth tokens in .env)."""

from typing import Optional
from datetime import datetime, timedelta
from config.settings import settings
import logging

logger = logging.getLogger("obra.google")


def _creds():
    if not settings.GOOGLE_ACCESS_TOKEN:
        return None
    try:
        from google.oauth2.credentials import Credentials
        return Credentials(
            token=settings.GOOGLE_ACCESS_TOKEN,
            refresh_token=settings.GOOGLE_REFRESH_TOKEN or None,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.GOOGLE_CLIENT_ID or None,
            client_secret=settings.GOOGLE_CLIENT_SECRET or None,
        )
    except Exception as e:
        logger.warning("Google creds error: %s", e)
        return None


async def gmail_list_unread(max_results: int = 5) -> str:
    creds = _creds()
    if not creds:
        return (
            "Gmail not configured. Set GOOGLE_ACCESS_TOKEN "
            "(and optionally REFRESH_TOKEN, CLIENT_ID, CLIENT_SECRET). See Api.md."
        )
    try:
        from googleapiclient.discovery import build
        import asyncio

        def _run():
            svc = build("gmail", "v1", credentials=creds, cache_discovery=False)
            res = svc.users().messages().list(userId="me", q="is:unread", maxResults=max_results).execute()
            msgs = res.get("messages", [])
            lines = []
            for m in msgs:
                full = svc.users().messages().get(userId="me", id=m["id"], format="metadata", metadataHeaders=["Subject", "From"]).execute()
                headers = {h["name"]: h["value"] for h in full.get("payload", {}).get("headers", [])}
                lines.append(f"- From: {headers.get('From','?')} | {headers.get('Subject','(no subject)')}")
            return "\n".join(lines) or "No unread messages."

        return await asyncio.to_thread(_run)
    except Exception as e:
        return f"Gmail error: {e}"


async def gmail_send(to: str, subject: str, body: str) -> str:
    creds = _creds()
    if not creds:
        return "Gmail not configured. See Api.md."
    try:
        from googleapiclient.discovery import build
        from email.mime.text import MIMEText
        import base64
        import asyncio

        def _run():
            svc = build("gmail", "v1", credentials=creds, cache_discovery=False)
            msg = MIMEText(body)
            msg["to"] = to
            msg["subject"] = subject
            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
            svc.users().messages().send(userId="me", body={"raw": raw}).execute()
            return f"Email sent to {to}: {subject}"

        return await asyncio.to_thread(_run)
    except Exception as e:
        return f"Gmail send error: {e}"


async def calendar_upcoming(days: int = 7) -> str:
    creds = _creds()
    if not creds:
        return "Calendar not configured. Set GOOGLE_* tokens. See Api.md."
    try:
        from googleapiclient.discovery import build
        import asyncio

        def _run():
            svc = build("calendar", "v3", credentials=creds, cache_discovery=False)
            now = datetime.utcnow().isoformat() + "Z"
            end = (datetime.utcnow() + timedelta(days=days)).isoformat() + "Z"
            events = svc.events().list(
                calendarId="primary",
                timeMin=now,
                timeMax=end,
                maxResults=10,
                singleEvents=True,
                orderBy="startTime",
            ).execute().get("items", [])
            lines = []
            for e in events:
                start = e["start"].get("dateTime", e["start"].get("date"))
                lines.append(f"- {start}: {e.get('summary', '(no title)')}")
            return "\n".join(lines) or "No upcoming events."

        return await asyncio.to_thread(_run)
    except Exception as e:
        return f"Calendar error: {e}"


async def calendar_create(summary: str, start_iso: str, end_iso: str = "") -> str:
    creds = _creds()
    if not creds:
        return "Calendar not configured. See Api.md."
    try:
        from googleapiclient.discovery import build
        import asyncio

        def _run():
            svc = build("calendar", "v3", credentials=creds, cache_discovery=False)
            if not end_iso:
                # default 1 hour
                try:
                    st = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
                    en = (st + timedelta(hours=1)).isoformat()
                except Exception:
                    en = start_iso
            else:
                en = end_iso
            body = {
                "summary": summary,
                "start": {"dateTime": start_iso, "timeZone": "UTC"},
                "end": {"dateTime": en, "timeZone": "UTC"},
            }
            ev = svc.events().insert(calendarId="primary", body=body).execute()
            return f"Event created: {ev.get('htmlLink', summary)}"

        return await asyncio.to_thread(_run)
    except Exception as e:
        return f"Calendar create error: {e}"
