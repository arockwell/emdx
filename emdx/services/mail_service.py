"""Mail service - agent-to-agent communication via GitHub Issues.

Uses a dedicated GitHub Issues repo for point-to-point messaging between
teammates' Claude Code agents. Label-based routing, zero infrastructure.
"""

import json
import logging
import sqlite3
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from emdx.config.settings import get_db_path

logger = logging.getLogger(__name__)

# Fixed labels that must exist on the mail repo
FIXED_LABELS = [
    ("agent-mail", "Agent-to-agent mail message", "0075ca"),
    ("status:unread", "New unread message", "d93f0b"),
    ("status:read", "Message has been read", "0e8a16"),
]


@dataclass
class MailMessage:
    """A single mail message (GitHub issue)."""

    number: int
    title: str
    body: str
    sender: str
    recipient: str
    is_read: bool
    created_at: str
    updated_at: str
    comment_count: int
    labels: List[str] = field(default_factory=list)
    url: str = ""

    @classmethod
    def from_gh_json(cls, data: Dict[str, Any]) -> "MailMessage":
        """Create MailMessage from gh CLI JSON output."""
        labels = []
        label_data = data.get("labels", [])
        for label in label_data:
            if isinstance(label, dict) and label.get("name"):
                labels.append(label["name"])
            elif isinstance(label, str):
                labels.append(label)

        sender = ""
        recipient = ""
        is_read = True
        for lbl in labels:
            if lbl.startswith("from:"):
                sender = lbl[5:]
            elif lbl.startswith("to:"):
                recipient = lbl[3:]
            elif lbl == "status:unread":
                is_read = False
            elif lbl == "status:read":
                is_read = True

        return cls(
            number=data.get("number", 0),
            title=data.get("title", ""),
            body=data.get("body", ""),
            sender=sender,
            recipient=recipient,
            is_read=is_read,
            created_at=data.get("createdAt", ""),
            updated_at=data.get("updatedAt", ""),
            comment_count=data.get("comments", 0)
            if isinstance(data.get("comments"), int)
            else data.get("comments", {}).get("totalCount", 0)
            if isinstance(data.get("comments"), dict)
            else 0,
            labels=labels,
            url=data.get("url", ""),
        )


@dataclass
class MailThread:
    """A mail thread (issue + comments)."""

    message: MailMessage
    comments: List[Dict[str, Any]] = field(default_factory=list)


class MailService:
    """Service for agent mail operations via gh CLI."""

    def __init__(self, repo: Optional[str] = None):
        self._repo = repo
        self._current_user: Optional[str] = None

    @property
    def repo(self) -> Optional[str]:
        if self._repo is None:
            self._repo = get_mail_config_repo()
        return self._repo

    def _run_gh_sync(
        self, args: List[str], timeout: int = 30
    ) -> Tuple[bool, str, str]:
        """Run a gh CLI command synchronously.

        Returns:
            Tuple of (success, stdout, stderr)
        """
        try:
            cmd = ["gh"] + args
            logger.debug(f"Running gh command: {' '.join(cmd)}")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            if result.returncode != 0:
                logger.warning(f"gh command failed: {result.stderr}")
                return False, result.stdout, result.stderr

            return True, result.stdout, result.stderr

        except FileNotFoundError:
            return False, "", "gh CLI not found. Install from https://cli.github.com/"
        except subprocess.TimeoutExpired:
            return False, "", f"Command timed out after {timeout}s"
        except Exception as e:
            logger.error(f"Error running gh command: {e}")
            return False, "", str(e)

    def get_current_user(self) -> Optional[str]:
        """Get the current authenticated GitHub user."""
        if self._current_user:
            return self._current_user

        success, stdout, stderr = self._run_gh_sync(
            ["api", "user", "--jq", ".login"]
        )
        if success and stdout.strip():
            self._current_user = stdout.strip()
            return self._current_user

        return None

    def ensure_labels(self) -> Tuple[int, int, int]:
        """Create fixed labels on the mail repo (idempotent).

        Returns:
            Tuple of (created, existing, errors)
        """
        if not self.repo:
            return 0, 0, 1

        created = 0
        existing = 0
        errors = 0

        for name, description, color in FIXED_LABELS:
            success, stdout, stderr = self._run_gh_sync(
                [
                    "label", "create", name,
                    "--description", description,
                    "--color", color,
                    "--repo", self.repo,
                    "--force",
                ]
            )
            if success:
                if "already exists" in stderr.lower():
                    existing += 1
                else:
                    created += 1
            else:
                errors += 1

        return created, existing, errors

    def ensure_user_labels(self, username: str) -> None:
        """Create from:/to: labels for a user (idempotent)."""
        if not self.repo:
            return

        for prefix, color in [("from:", "c5def5"), ("to:", "bfd4f2")]:
            label_name = f"{prefix}{username}"
            self._run_gh_sync(
                [
                    "label", "create", label_name,
                    "--description", f"Messages {prefix.rstrip(':')} {username}",
                    "--color", color,
                    "--repo", self.repo,
                    "--force",
                ]
            )

    def send_message(
        self,
        to: str,
        subject: str,
        body: str,
        doc_id: Optional[int] = None,
    ) -> Tuple[bool, Optional[int], str]:
        """Send a message (create a GitHub issue).

        Returns:
            Tuple of (success, issue_number, message)
        """
        if not self.repo:
            return False, None, "Mail repo not configured. Run: emdx mail setup <org/repo>"

        sender = self.get_current_user()
        if not sender:
            return False, None, "Could not determine GitHub username. Run: gh auth login"

        # Ensure user labels exist
        self.ensure_user_labels(sender)
        self.ensure_user_labels(to)

        # Format the message body
        formatted_body = _format_message_body(body, sender, doc_id)

        # Create the issue with labels
        labels = f"agent-mail,from:{sender},to:{to},status:unread"

        success, stdout, stderr = self._run_gh_sync(
            [
                "issue", "create",
                "--title", subject,
                "--body", formatted_body,
                "--label", labels,
                "--repo", self.repo,
            ]
        )

        if success:
            # Extract issue number from URL output
            url = stdout.strip()
            try:
                issue_number = int(url.rstrip("/").split("/")[-1])
                return True, issue_number, url
            except (ValueError, IndexError):
                return True, None, url

        return False, None, stderr

    def list_inbox(
        self,
        limit: int = 20,
        unread_only: bool = False,
        from_user: Optional[str] = None,
    ) -> List[MailMessage]:
        """List messages in inbox (issues labeled to:<current_user>).

        Returns:
            List of MailMessage objects
        """
        if not self.repo:
            return []

        me = self.get_current_user()
        if not me:
            return []

        # Build label filter
        label_parts = [f"agent-mail", f"to:{me}"]
        if unread_only:
            label_parts.append("status:unread")
        if from_user:
            label_parts.append(f"from:{from_user}")

        labels_arg = ",".join(label_parts)

        success, stdout, stderr = self._run_gh_sync(
            [
                "issue", "list",
                "--label", labels_arg,
                "--json", "number,title,body,labels,createdAt,updatedAt,comments,url",
                "--limit", str(limit),
                "--state", "open",
                "--repo", self.repo,
            ]
        )

        if not success:
            logger.error(f"Failed to list inbox: {stderr}")
            return []

        try:
            data = json.loads(stdout) if stdout.strip() else []
            return [MailMessage.from_gh_json(item) for item in data]
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse inbox JSON: {e}")
            return []

    def get_thread(self, issue_number: int) -> Optional[MailThread]:
        """Get a message thread (issue + comments).

        Returns:
            MailThread or None if not found
        """
        if not self.repo:
            return None

        # Get issue details
        success, stdout, stderr = self._run_gh_sync(
            [
                "issue", "view", str(issue_number),
                "--json", "number,title,body,labels,createdAt,updatedAt,comments,url",
                "--repo", self.repo,
            ]
        )

        if not success:
            return None

        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            return None

        message = MailMessage.from_gh_json(data)

        # Parse comments from the issue data
        comments = []
        raw_comments = data.get("comments", [])
        if isinstance(raw_comments, list):
            for c in raw_comments:
                if isinstance(c, dict):
                    comments.append({
                        "author": c.get("author", {}).get("login", "")
                        if isinstance(c.get("author"), dict)
                        else str(c.get("author", "")),
                        "body": c.get("body", ""),
                        "created_at": c.get("createdAt", ""),
                    })

        return MailThread(message=message, comments=comments)

    def mark_read(self, issue_number: int) -> bool:
        """Mark a message as read (swap status label)."""
        return self._swap_status_label(issue_number, "read")

    def _swap_status_label(self, issue_number: int, new_status: str) -> bool:
        """Remove old status:* labels and add new one."""
        if not self.repo:
            return False

        # Remove the opposite status label
        old_status = "unread" if new_status == "read" else "read"
        self._run_gh_sync(
            [
                "issue", "edit", str(issue_number),
                "--remove-label", f"status:{old_status}",
                "--repo", self.repo,
            ]
        )

        # Add new status label
        success, _, _ = self._run_gh_sync(
            [
                "issue", "edit", str(issue_number),
                "--add-label", f"status:{new_status}",
                "--repo", self.repo,
            ]
        )

        return success

    def reply_to_message(
        self,
        issue_number: int,
        body: str,
        close: bool = False,
    ) -> Tuple[bool, str]:
        """Reply to a message (add comment to issue).

        Returns:
            Tuple of (success, message)
        """
        if not self.repo:
            return False, "Mail repo not configured."

        sender = self.get_current_user()
        if not sender:
            return False, "Could not determine GitHub username."

        formatted = _format_message_body(body, sender)

        success, stdout, stderr = self._run_gh_sync(
            [
                "issue", "comment", str(issue_number),
                "--body", formatted,
                "--repo", self.repo,
            ]
        )

        if not success:
            return False, stderr

        # Mark as unread for the other party (they have a new reply)
        self._swap_status_label(issue_number, "unread")

        if close:
            self._run_gh_sync(
                [
                    "issue", "close", str(issue_number),
                    "--repo", self.repo,
                ]
            )

        return True, stdout.strip() if stdout.strip() else "Reply sent"

    def get_unread_count(self) -> int:
        """Get count of unread messages."""
        messages = self.list_inbox(limit=100, unread_only=True)
        return len(messages)

    def record_read_receipt(
        self, issue_number: int, saved_doc_id: Optional[int] = None
    ) -> None:
        """Record that a message was read locally."""
        conn = sqlite3.connect(get_db_path())
        try:
            conn.execute(
                """INSERT OR REPLACE INTO mail_read_receipts
                   (issue_number, repo, read_at, saved_doc_id)
                   VALUES (?, ?, CURRENT_TIMESTAMP, ?)""",
                (issue_number, self.repo or "", saved_doc_id),
            )
            conn.commit()
        finally:
            conn.close()

    def get_read_receipt(self, issue_number: int) -> Optional[Dict[str, Any]]:
        """Check if a message was previously read/saved."""
        conn = sqlite3.connect(get_db_path())
        try:
            cursor = conn.execute(
                "SELECT issue_number, repo, read_at, saved_doc_id FROM mail_read_receipts WHERE issue_number = ?",
                (issue_number,),
            )
            row = cursor.fetchone()
            if row:
                return {
                    "issue_number": row[0],
                    "repo": row[1],
                    "read_at": row[2],
                    "saved_doc_id": row[3],
                }
            return None
        finally:
            conn.close()


def get_mail_config_repo() -> Optional[str]:
    """Get the configured mail repo from database."""
    try:
        conn = sqlite3.connect(get_db_path())
        cursor = conn.execute(
            "SELECT value FROM mail_config WHERE key = 'repo'"
        )
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None
    except Exception:
        return None


def set_mail_config_repo(repo: str) -> None:
    """Set the mail repo in database."""
    conn = sqlite3.connect(get_db_path())
    conn.execute(
        "INSERT OR REPLACE INTO mail_config (key, value, updated_at) VALUES ('repo', ?, CURRENT_TIMESTAMP)",
        (repo,),
    )
    conn.commit()
    conn.close()


def _format_message_body(
    body: str,
    sender: str,
    doc_id: Optional[int] = None,
    project: Optional[str] = None,
) -> str:
    """Format a message body with metadata header."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    header_lines = [f"Sender: @{sender}"]
    if project:
        header_lines.append(f"Project: {project}")
    if doc_id is not None:
        header_lines.append(f"Doc Reference: emdx:#{doc_id}")
    header_lines.append(f"Sent: {now}")
    header_lines.append("Via: emdx mail")

    header = "\n".join(header_lines)

    return f"```\n{header}\n```\n\n{body}"


# Singleton
_mail_service: Optional[MailService] = None


def get_mail_service() -> MailService:
    """Get the singleton MailService instance."""
    global _mail_service
    if _mail_service is None:
        _mail_service = MailService()
    return _mail_service
