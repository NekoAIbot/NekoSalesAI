"""What our emails say.

Separate from ``app.mail.transport`` so that changing the words is never a change
to the delivery mechanism, and so every message a customer can receive is
readable in one file rather than scattered across the code that triggers it.

House style, and the reason for it:

Plain text. A workspace credential arriving as a marketing-styled HTML email is
the shape of a phishing message, and we are asking people to trust an address
they have never received mail from before.

The subject says what happened. "Your workspace is ready" is a fact; "Welcome to
the future of sales" is an announcement, and the person reading it has just paid
money and wants to know whether it worked.

No invented figures. Every amount comes from the order or the plan it is built
from — the same rule the agent follows, for the same reason.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config.settings import settings
from app.mail.transport import Message
from app.products.config import format_money


def _signoff() -> str:
    return f"— {settings.MAIL_FROM_NAME}\n{settings.MAIL_FROM}"


@dataclass(frozen=True)
class AgentCredentials:
    """One agent's own way in.

    Each agent bought on one order gets its own key and its own widget token,
    so this is per-agent rather than per-purchase. A shared key would mean a
    customer could not revoke their support agent without silencing their sales
    agent too.
    """

    # What the agent is, in the customer's terms: "AI Sales Representative".
    label: str

    api_key: str | None = None
    widget_token: str | None = None


def receipt(
    *,
    to: str,
    company_name: str,
    plan_name: str,
    amount_minor: int,
    currency: str,
    reference: str,
    workspace_profile_id: int | None = None,
) -> Message:
    """Confirmation that money moved and what it bought.

    The amount is passed in rather than looked up, so this function cannot
    disagree with the order it is describing.
    """
    amount = format_money(amount_minor, currency)

    body = (
        f"Thanks — your payment went through.\n\n"
        f"  What you bought   {plan_name}\n"
        f"  Amount            {amount}\n"
        f"  Reference         {reference}\n\n"
        f"Your workspace for {company_name} is being set up now. You will get a "
        f"second email with your login as soon as it is ready, which is usually "
        f"a few seconds.\n\n"
        f"Keep this email — the reference above is what we need if you ever ask "
        f"us about this payment.\n\n"
        f"{_signoff()}\n"
    )

    return Message(
        to=to,
        subject=f"Your {plan_name} payment — {amount}",
        body=body,
        workspace_profile_id=workspace_profile_id,
    )


def credentials(
    *,
    to: str,
    company_name: str,
    temporary_password: str | None,
    api_key: str | None = None,
    widget_token: str | None = None,
    agents: tuple[AgentCredentials, ...] = (),
    workspace_profile_id: int | None = None,
) -> Message:
    """The one email that carries secrets, and the only time they exist in full.

    Both the API key and the temporary password are shown once and stored only
    as hashes, so this message cannot be regenerated — which is exactly why it
    says so rather than letting someone discover it later.

    ``agents`` carries one entry per agent bought. One order can buy several,
    and each has its own key and widget token, so a single pair of kwargs cannot
    describe the purchase: the second agent's credentials would simply be
    missing from the only email that will ever contain them. ``api_key`` and
    ``widget_token`` are the one-agent spelling of the same thing.
    """
    if not agents and (api_key or widget_token):
        agents = (AgentCredentials(label="", api_key=api_key, widget_token=widget_token),)

    lines = [
        f"Your workspace for {company_name} is ready.\n",
        f"Sign in at {settings.PUBLIC_BASE_URL}/desk with this email address.\n",
    ]

    if temporary_password:
        lines.append(
            f"  Temporary password   {temporary_password}\n\n"
            f"Change it after your first sign-in. We cannot send it again — it is "
            f"stored only as a hash, so a replacement is a reset, not a copy.\n"
        )

    # Named only when there is more than one, so a customer who bought a single
    # agent is not made to read a heading that distinguishes it from nothing.
    name_them = len(agents) > 1

    for agent in agents:
        if name_them and agent.label:
            lines.append(f"--- {agent.label} ---\n")

        if agent.api_key:
            lines.append(
                f"  API key              {agent.api_key}\n\n"
                f"This is shown once and never again, for the same reason. It "
                f"authenticates your own integrations; treat it like a password and "
                f"keep it on your server, never in a web page.\n"
            )

        if agent.widget_token:
            what = f"your {agent.label}" if name_them and agent.label else "your agent"
            lines.append(
                f"To put {what} on your website, paste this before </body>:\n\n"
                f'  <script src="{settings.PUBLIC_BASE_URL}/static/js/widget.js"\n'
                f'          data-token="{agent.widget_token}" async></script>\n\n'
                "Unlike the API key, this token is safe in your page source. It can "
                "start a conversation and nothing else.\n"
            )

    lines.append(f"\n{_signoff()}\n")

    return Message(
        to=to,
        subject=f"{company_name} — your workspace is ready",
        body="\n".join(lines),
        workspace_profile_id=workspace_profile_id,
    )


def follow_up(
    *,
    to: str,
    subject: str,
    body: str,
    workspace_profile_id: int | None = None,
) -> Message:
    """A scheduled post-sale message.

    The wording comes from ``app.followups.rules``, which is where the follow-up
    calendar and its copy already live. This exists so the runner has one way to
    turn a rule into something sendable.
    """
    return Message(
        to=to,
        subject=subject,
        body=f"{body}\n\n{_signoff()}\n",
        workspace_profile_id=workspace_profile_id,
    )
