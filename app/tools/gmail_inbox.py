"""Read-only Gmail IMAP inbox access with safe text extraction."""
from __future__ import annotations

import email
import html
import imaplib
import os
import re
from email.header import decode_header
from email.message import Message
from html.parser import HTMLParser
from typing import Any


class _HTMLTextParser(HTMLParser):
    BLOCK_TAGS = {
        "br", "p", "div", "li", "tr", "td", "th", "h1", "h2", "h3", "h4",
        "h5", "h6", "blockquote", "section", "article", "header", "footer"
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data)

    def text(self) -> str:
        text = html.unescape(" ".join(self.parts))
        text = re.sub(r"\r\n?", "\n", text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n[ \t]+", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


class GmailInbox:
    def __init__(self) -> None:
        self.username = os.environ.get("SENDER_EMAIL")
        self.password = os.environ.get("SENDER_APP_PASSWORD")
        self.server = os.environ.get("IMAP_SERVER", "imap.gmail.com")
        self.port = int(os.environ.get("IMAP_PORT", "993"))

    @staticmethod
    def _decode(value: str | None) -> str:
        if not value:
            return ""
        parts = []
        for chunk, encoding in decode_header(value):
            if isinstance(chunk, bytes):
                parts.append(chunk.decode(encoding or "utf-8", errors="replace"))
            else:
                parts.append(chunk)
        return "".join(parts)

    @staticmethod
    def _html_to_text(source: str) -> str:
        parser = _HTMLTextParser()
        try:
            parser.feed(source)
            parser.close()
            text = parser.text()
        except Exception:
            text = re.sub(r"<[^>]+>", " ", source)
            text = html.unescape(text)
            text = re.sub(r"\s+", " ", text).strip()
        return text

    @classmethod
    def _clean_text(cls, text: str, content_type: str) -> str:
        if content_type == "text/html" or re.search(r"<(?:html|body|table|div|p|style)\b", text, re.I):
            text = cls._html_to_text(text)
        text = text.replace("\u00a0", " ")
        text = re.sub(r"\r\n?", "\n", text)
        # Remove common quoted-history lines from replies.
        lines = []
        for line in text.splitlines():
            if re.match(r"^On .+ wrote:$", line.strip(), re.I):
                break
            if line.strip().startswith(">"):
                continue
            lines.append(line.rstrip())
        text = "\n".join(lines)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        return text

    @classmethod
    def _text_from_message(cls, message: Message) -> str:
        plain_parts: list[str] = []
        html_parts: list[str] = []
        if message.is_multipart():
            for part in message.walk():
                if part.get_content_disposition() == "attachment":
                    continue
                content_type = part.get_content_type()
                if content_type not in {"text/plain", "text/html"}:
                    continue
                payload = part.get_payload(decode=True)
                if not isinstance(payload, bytes):
                    continue
                text = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
                if content_type == "text/plain":
                    plain_parts.append(text)
                else:
                    html_parts.append(text)
        else:
            payload = message.get_payload(decode=True)
            if isinstance(payload, bytes):
                text = payload.decode(message.get_content_charset() or "utf-8", errors="replace")
            else:
                text = str(message.get_payload() or "")
            if message.get_content_type() == "text/html":
                html_parts.append(text)
            else:
                plain_parts.append(text)

        if plain_parts:
            return cls._clean_text("\n\n".join(plain_parts), "text/plain")
        if html_parts:
            return cls._clean_text("\n\n".join(html_parts), "text/html")
        return ""

    def _validate_config(self) -> None:
        if not self.username or not self.password:
            raise RuntimeError("SENDER_EMAIL / SENDER_APP_PASSWORD not set. Add them to the local .env file.")

    def fetch_unread(self, limit: int = 10) -> list[dict[str, Any]]:
        self._validate_config()
        mailbox = imaplib.IMAP4_SSL(self.server, self.port)
        try:
            mailbox.login(self.username, self.password)
            status, _ = mailbox.select("INBOX", readonly=True)
            if status != "OK":
                raise RuntimeError("Could not open Gmail INBOX.")
            status, data = mailbox.search(None, "UNSEEN")
            if status != "OK":
                raise RuntimeError("Could not search Gmail inbox.")

            ids = data[0].split()[-limit:]
            messages: list[dict[str, Any]] = []
            for message_id in reversed(ids):
                status, fetched = mailbox.fetch(message_id, "(RFC822)")
                if status != "OK":
                    continue
                raw = next((part[1] for part in fetched if isinstance(part, tuple)), None)
                if not isinstance(raw, bytes):
                    continue
                parsed = email.message_from_bytes(raw)
                sender_name, sender_email = email.utils.parseaddr(parsed.get("From", ""))
                body = self._text_from_message(parsed)
                messages.append({
                    "id": message_id.decode("ascii", errors="ignore"),
                    "message_id": parsed.get("Message-ID", ""),
                    "from": parsed.get("From", ""),
                    "from_name": sender_name,
                    "from_email": sender_email.lower(),
                    "to": parsed.get("To", ""),
                    "subject": self._decode(parsed.get("Subject")),
                    "date": parsed.get("Date", ""),
                    "body": body,
                    "content_type": parsed.get_content_type(),
                })
            return messages
        finally:
            try:
                mailbox.logout()
            except Exception:
                pass
