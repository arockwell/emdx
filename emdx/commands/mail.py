"""Mail CLI commands - agent-to-agent communication via GitHub Issues."""

import sys
from typing import Optional

import typer
from rich.panel import Panel
from rich.table import Table

from emdx.utils.output import console

app = typer.Typer(help="Agent-to-agent mail via GitHub Issues")

ICONS = {"unread": "●", "read": "○", "reply": "↩", "mail": "📧"}


@app.command()
def setup(
    repo: str = typer.Argument(..., help="GitHub repo for mail (org/repo)"),
):
    """One-time setup: configure mail repo and create labels."""
    from emdx.services.mail_service import MailService, set_mail_config_repo

    # Validate repo format
    if "/" not in repo:
        console.print("[red]Error: repo must be in org/repo format[/red]")
        raise typer.Exit(1)

    service = MailService(repo=repo)

    # Verify gh auth
    user = service.get_current_user()
    if not user:
        console.print("[red]Error: not authenticated with gh CLI. Run: gh auth login[/red]")
        raise typer.Exit(1)

    console.print(f"[dim]Authenticated as @{user}[/dim]")
    console.print(f"[dim]Setting up mail repo: {repo}[/dim]")

    # Create labels
    created, existing, errors = service.ensure_labels()
    service.ensure_user_labels(user)

    if errors:
        console.print(f"[yellow]Warning: {errors} label(s) failed to create[/yellow]")

    # Save config
    set_mail_config_repo(repo)

    console.print(f"[green]✅ Mail configured[/green]")
    console.print(f"   Repo: {repo}")
    console.print(f"   Labels created: {created}, already existed: {existing}")
    console.print(f"   Your username: @{user}")


@app.command()
def send(
    to: str = typer.Argument(..., help="Recipient GitHub username"),
    subject: str = typer.Option(..., "-s", "--subject", help="Message subject"),
    body: Optional[str] = typer.Option(None, "-b", "--body", help="Message body"),
    doc: Optional[int] = typer.Option(None, "-d", "--doc", help="Attach emdx doc by ID"),
    stdin: bool = typer.Option(False, "--stdin", help="Read body from stdin"),
):
    """Send a message to a GitHub user."""
    from emdx.services.mail_service import get_mail_service

    service = get_mail_service()

    # Build message body
    msg_body = ""
    if stdin:
        msg_body = sys.stdin.read()
    elif body:
        msg_body = body
    elif doc:
        msg_body = ""  # doc content will be embedded
    else:
        console.print("[red]Error: provide --body, --doc, or --stdin[/red]")
        raise typer.Exit(1)

    # If doc reference, embed content
    if doc is not None:
        from emdx.models.documents import get_document

        document = get_document(str(doc))
        if document:
            doc_content = document.get("content", "")
            # Truncate at 60K chars
            if len(doc_content) > 60000:
                doc_content = doc_content[:60000] + "\n\n[... truncated at 60K chars]"
            if msg_body:
                msg_body += f"\n\n---\n\n**Attached doc #{doc}:** {document.get('title', 'Untitled')}\n\n{doc_content}"
            else:
                msg_body = f"**Attached doc #{doc}:** {document.get('title', 'Untitled')}\n\n{doc_content}"
        else:
            console.print(f"[yellow]Warning: doc #{doc} not found, sending without attachment[/yellow]")

    success, issue_number, result_msg = service.send_message(
        to=to, subject=subject, body=msg_body, doc_id=doc
    )

    if success:
        console.print(f"[green]✅ Message sent to @{to}[/green]")
        if issue_number:
            console.print(f"   Issue #{issue_number}")
        console.print(f"   {result_msg}")
    else:
        console.print(f"[red]Error: {result_msg}[/red]")
        raise typer.Exit(1)


@app.command()
def inbox(
    unread: bool = typer.Option(False, "-u", "--unread", help="Show only unread"),
    from_user: Optional[str] = typer.Option(None, "-f", "--from", help="Filter by sender"),
    limit: int = typer.Option(20, "-n", "--limit", help="Max messages to show"),
):
    """Check your inbox."""
    from emdx.services.mail_service import get_mail_service

    service = get_mail_service()

    if not service.repo:
        console.print("[red]Mail not configured. Run: emdx mail setup <org/repo>[/red]")
        raise typer.Exit(1)

    messages = service.list_inbox(
        limit=limit, unread_only=unread, from_user=from_user
    )

    if not messages:
        console.print("[dim]No messages[/dim]")
        return

    table = Table(title="Inbox")
    table.add_column("", width=2)
    table.add_column("#", width=6)
    table.add_column("From", width=15)
    table.add_column("Subject")
    table.add_column("Date", width=12)
    table.add_column("💬", width=3)

    for msg in messages:
        icon = ICONS["unread"] if not msg.is_read else ICONS["read"]
        style = "bold" if not msg.is_read else "dim"
        date_str = msg.created_at[:10] if msg.created_at else ""
        table.add_row(
            icon,
            str(msg.number),
            f"@{msg.sender}",
            msg.title,
            date_str,
            str(msg.comment_count) if msg.comment_count else "",
            style=style,
        )

    console.print(table)
    console.print(f"\n[dim]{len(messages)} message(s)[/dim]")


@app.command("read")
def read_msg(
    issue: int = typer.Argument(..., help="Issue number to read"),
    no_save: bool = typer.Option(False, "--no-save", help="Don't save to KB"),
    tags: Optional[str] = typer.Option(None, "--tags", help="Tags for saved doc (comma-sep)"),
):
    """Read a message thread. Auto-marks as read and saves to KB."""
    from emdx.services.mail_service import get_mail_service

    service = get_mail_service()

    if not service.repo:
        console.print("[red]Mail not configured. Run: emdx mail setup <org/repo>[/red]")
        raise typer.Exit(1)

    thread = service.get_thread(issue)
    if not thread:
        console.print(f"[red]Message #{issue} not found[/red]")
        raise typer.Exit(1)

    msg = thread.message

    # Display message
    console.print(Panel(
        f"[bold]{msg.title}[/bold]\n"
        f"[dim]From: @{msg.sender} → @{msg.recipient}[/dim]\n"
        f"[dim]Date: {msg.created_at}[/dim]\n"
        f"[dim]URL: {msg.url}[/dim]\n\n"
        f"{msg.body}",
        title=f"Message #{msg.number}",
    ))

    # Display replies
    if thread.comments:
        console.print(f"\n[bold]Replies ({len(thread.comments)}):[/bold]")
        for i, comment in enumerate(thread.comments, 1):
            console.print(Panel(
                f"[dim]@{comment.get('author', '?')} — {comment.get('created_at', '')[:19]}[/dim]\n\n"
                f"{comment.get('body', '')}",
                title=f"Reply #{i}",
            ))

    # Mark as read
    service.mark_read(issue)

    # Auto-save to KB unless --no-save
    saved_doc_id = None
    receipt = service.get_read_receipt(issue)

    if not no_save and (receipt is None or receipt.get("saved_doc_id") is None):
        from emdx.models.documents import save_document

        # Build content for saving
        content_parts = [msg.body]
        for comment in thread.comments:
            content_parts.append(
                f"\n---\n**@{comment.get('author', '?')}** ({comment.get('created_at', '')[:19]}):\n\n{comment.get('body', '')}"
            )
        content = "\n".join(content_parts)

        tag_list = ["notes"]
        if tags:
            tag_list = [t.strip() for t in tags.split(",") if t.strip()]

        saved_doc_id = save_document(
            title=f"Mail: {msg.title} (from @{msg.sender})",
            content=content,
        )
        console.print(f"[green]Saved to KB as doc #{saved_doc_id}[/green]")
    elif receipt and receipt.get("saved_doc_id"):
        console.print(f"[dim]Previously saved as doc #{receipt['saved_doc_id']}[/dim]")

    # Record read receipt
    service.record_read_receipt(issue, saved_doc_id)


@app.command()
def reply(
    issue: int = typer.Argument(..., help="Issue number to reply to"),
    body: Optional[str] = typer.Option(None, "-b", "--body", help="Reply body"),
    doc: Optional[int] = typer.Option(None, "-d", "--doc", help="Attach emdx doc by ID"),
    stdin: bool = typer.Option(False, "--stdin", help="Read body from stdin"),
    close: bool = typer.Option(False, "--close", help="Close the thread after reply"),
):
    """Reply to a message."""
    from emdx.services.mail_service import get_mail_service

    service = get_mail_service()

    # Build reply body
    reply_body = ""
    if stdin:
        reply_body = sys.stdin.read()
    elif body:
        reply_body = body
    elif doc:
        reply_body = ""
    else:
        console.print("[red]Error: provide --body, --doc, or --stdin[/red]")
        raise typer.Exit(1)

    # Embed doc if specified
    if doc is not None:
        from emdx.models.documents import get_document

        document = get_document(str(doc))
        if document:
            doc_content = document.get("content", "")
            if len(doc_content) > 60000:
                doc_content = doc_content[:60000] + "\n\n[... truncated at 60K chars]"
            if reply_body:
                reply_body += f"\n\n---\n\n**Attached doc #{doc}:** {document.get('title', 'Untitled')}\n\n{doc_content}"
            else:
                reply_body = f"**Attached doc #{doc}:** {document.get('title', 'Untitled')}\n\n{doc_content}"
        else:
            console.print(f"[yellow]Warning: doc #{doc} not found[/yellow]")

    success, result_msg = service.reply_to_message(
        issue_number=issue, body=reply_body, close=close
    )

    if success:
        console.print(f"[green]✅ Reply sent to #{issue}[/green]")
        if close:
            console.print("[dim]Thread closed[/dim]")
    else:
        console.print(f"[red]Error: {result_msg}[/red]")
        raise typer.Exit(1)


@app.command()
def status():
    """Show mail config and unread count."""
    from emdx.services.mail_service import get_mail_config_repo, get_mail_service

    repo = get_mail_config_repo()
    if not repo:
        console.print("[yellow]Mail not configured[/yellow]")
        console.print("Run: [cyan]emdx mail setup <org/repo>[/cyan]")
        return

    service = get_mail_service()
    user = service.get_current_user()
    unread = service.get_unread_count()

    console.print(f"[bold]Mail Status[/bold]")
    console.print(f"  Repo: {repo}")
    console.print(f"  User: @{user}" if user else "  User: [red]not authenticated[/red]")

    if unread > 0:
        console.print(f"  Unread: [bold yellow]{unread}[/bold yellow]")
    else:
        console.print(f"  Unread: [green]0[/green]")
