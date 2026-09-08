"""How a customer actually gets their agent onto their site.

This module exists because of one line. The delivery message used to say "paste
your widget snippet into your site", which is instruction only to someone who
already knew the answer: it names the thing to do and none of the doing. A shop
owner who has just paid ₦148,000 does not know where a snippet lives, what
``</body>`` means, or that WordPress hides the file behind Appearance → Theme
File Editor. The gap between "your workspace is live" and a working chat button
is the gap where a paid customer quietly gives up, and nothing in the product was
helping them across it.

So the guidance is written out per platform, in the words the platform's own menus
use — "Online Store → Themes → ⋯ → Edit code", not "edit your theme". The steps
are checkable against a real admin panel, which is the standard: a step someone
cannot follow while looking at their screen is not a step.

Kept as its own module, pure and free of database and clock, for three reasons
beyond tidiness:

* The delivery message, the credentials email and the day-1 follow-up all need
  to say the same thing, and three copies of install instructions would drift
  until two of them were wrong.
* Nera has to answer "the button isn't showing up" without handing the customer
  to a person. Answering that well means reasoning over the same list of
  platforms and the same failure modes it just sent them — so the troubleshooting
  branches are data here rather than prose buried in a message template.
* It is text, so it is testable. ``test_install.py`` asserts that a customer on
  each platform is told which menu to open, which is the kind of claim that rots
  silently inside an f-string.

What is deliberately *not* here: self-serve Telegram and WhatsApp setup. Those
channels are sold and priced, but provisioning currently issues a widget token
and nothing else — no per-customer bot exists to give instructions for. Writing
confident steps for a flow the backend cannot complete would be the same species
of lie as the spinner that started all of this, so the messenger section says
what is true and offers the first real step instead.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config.settings import settings

# Telegram rejects a sendMessage over 4096 characters outright, and WhatsApp's
# body limit is the same. Full install guidance runs past that, so the delivery
# is composed as several messages rather than one — see ``MESSAGE_LIMIT`` users
# in app.messaging.clients.
MESSAGE_LIMIT = 4096


@dataclass(frozen=True)
class Platform:
    """One website builder, and the exact route through its admin to the footer."""

    key: str
    label: str
    steps: tuple[str, ...]
    note: str = ""

    def render(self) -> str:
        lines = [f"  {self.label}"]
        lines.extend(f"    {index}. {step}" for index, step in enumerate(self.steps, 1))

        if self.note:
            lines.append(f"    Note: {self.note}")

        return "\n".join(lines)


# Ordered by how likely a Nigerian small business is to be on it, because the
# first entry is the one most people will read before deciding whether the rest
# applies to them.
PLATFORMS: tuple[Platform, ...] = (
    Platform(
        key="wordpress",
        label="WordPress",
        steps=(
            "In your dashboard, go to Plugins → Add New Plugin and search for "
            "\"WPCode\". Install it, then Activate.",
            "Go to Code Snippets → Header & Footer.",
            "Paste the snippet into the box labelled Footer — not Header, not "
            "Body. Footer is the one that runs before </body>.",
            "Click Save Changes.",
        ),
        note=(
            "you can instead edit Appearance → Theme File Editor → footer.php and "
            "paste above </body>, but a theme update wipes that out. The plugin "
            "route survives updates."
        ),
    ),
    Platform(
        key="shopify",
        label="Shopify",
        steps=(
            "Go to Online Store → Themes.",
            "Next to your live theme, click the ⋯ button, then Edit code.",
            "Under Layout, open theme.liquid.",
            "Scroll to the very bottom, find the line that says </body>, and "
            "paste the snippet on the line just above it.",
            "Click Save.",
        ),
    ),
    Platform(
        key="wix",
        label="Wix",
        steps=(
            "Go to Settings → Custom Code (it is under Advanced).",
            "Click + Add Custom Code and paste the snippet in.",
            "Set \"Add Code to Pages\" to All pages.",
            "Set \"Place Code in\" to Body - end.",
            "Click Apply.",
        ),
    ),
    Platform(
        key="squarespace",
        label="Squarespace",
        steps=(
            "Go to Settings → Advanced → Code Injection.",
            "Paste the snippet into the Footer box.",
            "Click Save.",
        ),
        note=(
            "Code Injection needs a Business plan or higher. On a Personal plan "
            "the menu is not there — tell me and I will give you the alternative."
        ),
    ),
    Platform(
        key="webflow",
        label="Webflow",
        steps=(
            "Go to Project Settings → Custom Code.",
            "Paste the snippet into Footer Code.",
            "Click Save Changes.",
            "Publish the site. The change does not go live until you publish.",
        ),
    ),
    Platform(
        key="html",
        label="A site you or a developer built by hand",
        steps=(
            "Open each page's .html file in your editor.",
            "Find the closing </body> tag near the bottom and paste the snippet "
            "on the line directly above it.",
            "Upload the changed files to your host.",
        ),
        note=(
            "if your pages share one footer file or include, paste it there once "
            "instead of on every page."
        ),
    ),
)


# The three things that actually go wrong, in the order they go wrong. Data
# rather than prose because Nera answers "it is not showing up" by walking these
# with the customer, and it can only do that if it can read them.
TROUBLESHOOTING: tuple[tuple[str, str], ...] = (
    (
        "the snippet went into the header instead of the footer",
        "Move it to the Footer box. In the header it runs before the page exists "
        "and has nothing to attach the button to.",
    ),
    (
        "the site has not been republished, or you are seeing a cached copy",
        "Publish the site, then hard-refresh: Ctrl+Shift+R on Windows, "
        "Cmd+Shift+R on a Mac. If you run a caching plugin, clear its cache too.",
    ),
    (
        "only part of the snippet was copied",
        "It has to start with <script and end with </script>, and contain both "
        "the src and the data-token. A copy that stops at the line break is the "
        "commonest version of this.",
    ),
)


def platform_for(key: str) -> Platform | None:
    """One platform's steps, by key, or None if we do not have that one.

    ``PLATFORMS`` is ordered rather than keyed because the delivery message reads
    it in order, and the order carries meaning — the first entry is the one most
    customers will read before deciding whether the rest applies to them. This is
    the lookup the support path needs on top of that, kept here so there is still
    one table of install steps rather than a second copy keyed differently.

    Accepts whatever the customer's platform was recorded as, case and spacing
    included, so a stored "WordPress" or " shopify " still finds its steps.
    """
    wanted = (key or "").strip().lower().replace(" ", "")

    if not wanted:
        return None

    for platform in PLATFORMS:
        if platform.key == wanted:
            return platform

    return None


def widget_snippet(token: str) -> str:
    """The two lines the customer pastes.

    The token is in here rather than replaced with a placeholder because it is
    not a secret — it ends up in page source by design, and it authorises
    starting a conversation and nothing else. Making them go and look it up would
    add a step for no gain, and a placeholder is a thing people paste by mistake.
    """
    base = settings.PUBLIC_BASE_URL.rstrip("/")

    return (
        f'<script src="{base}/static/js/widget.js"\n'
        f'        data-token="{token}" async></script>'
    )


def sign_in_url() -> str:
    """Where the customer's login actually is.

    Named once, here, because it was wrong in two places at once: the delivery
    message sent buyers to ``/dashboard`` and the credentials email to ``/desk``,
    and only one of those is a route that exists. A paying customer following the
    chat message landed on a 404.
    """
    return f"{settings.PUBLIC_BASE_URL.rstrip('/')}/desk"


def website_steps(agents: tuple[tuple[str, str], ...]) -> str:
    """Full instructions for putting the widget on a site.

    ``agents`` is (name, widget_token) per agent bought, so a customer who bought
    both a sales rep and a support agent is given both snippets, labelled. One
    snippet with a vague "repeat for the other one" is how somebody ends up with
    the same agent on the page twice.
    """
    with_tokens = [(name, token) for name, token in agents if token]

    if not with_tokens:
        return ""

    lines = ["── Putting your agent on your website ──", ""]

    if len(with_tokens) == 1:
        name, token = with_tokens[0]
        lines += [
            f"1. Copy this snippet. It is {name}'s, and it already has your own "
            "token in it:",
            "",
            *(f"     {line}" for line in widget_snippet(token).splitlines()),
            "",
            f"   It is also in the email, and on your agent's page at "
            f"{sign_in_url()} under Widget, so you do not have to type it.",
        ]
    else:
        lines += [
            "1. Copy the snippet for whichever agent you want on the page. Each "
            "one is different — the token is what tells the page which of your "
            "agents it is talking to:",
            "",
        ]

        for name, token in with_tokens:
            lines.append(f"   {name}:")
            lines += [f"     {line}" for line in widget_snippet(token).splitlines()]
            lines.append("")

        lines.append(
            f"   Both are in the email, and on each agent's page at "
            f"{sign_in_url()} under Widget."
        )

    lines += [
        "",
        "2. Paste it into your site just before the closing </body> tag. Where "
        "that is depends on what your site is built with — find yours:",
        "",
    ]

    lines.extend(platform.render() + "\n" for platform in PLATFORMS)

    lines += [
        "3. Open your site in a new tab and reload it. A chat button appears in "
        "the bottom-right corner. Send it a message to check — that conversation "
        f"shows up on your desk at {sign_in_url()}.",
        "",
        "If the button does not appear, it is almost always one of three things:",
        "",
    ]

    lines.extend(
        f"  – {cause}\n    {fix}" for cause, fix in TROUBLESHOOTING
    )

    lines += [
        "",
        "Tell me which platform you are on and what you are seeing, and I will "
        "work through it with you.",
    ]

    return "\n".join(lines)


def messenger_steps(channels: tuple[str, ...]) -> str:
    """What to say to someone who bought Telegram or WhatsApp.

    Honest rather than complete, on purpose. Both channels are priced and sold,
    and provisioning issues a widget token and nothing else — there is no
    per-customer bot for these instructions to point at yet. So this says the
    website is live now, names the one thing only the customer can do (a bot has
    to be created from their own Telegram account, because the messages belong to
    their business and not to ours), and offers to take them through the rest.

    It promises no timeline and describes no screen that does not exist. When
    per-customer bot provisioning ships, this is the function that grows steps.
    """
    wanted = [channel for channel in ("telegram", "whatsapp") if channel in channels]

    if not wanted:
        return ""

    labels = {"telegram": "Telegram", "whatsapp": "WhatsApp"}
    named = " and ".join(labels[channel] for channel in wanted)

    lines = [f"── {named} ──", ""]

    lines.append(
        f"You bought {named} as well, and that part is not a snippet you paste — "
        "it needs a setup step I do together with you, because the account has to "
        "belong to your business rather than to me."
    )
    lines.append("")

    if "telegram" in wanted:
        lines += [
            "For Telegram, the one piece only you can create:",
            "",
            "  1. Open Telegram and search for @BotFather — the verified one, "
            "with the blue tick.",
            "  2. Send it /newbot. It asks for a display name (what your "
            "customers will see) and then a username, which has to end in "
            "\"bot\".",
            "  3. It replies with a token — a long line starting with numbers, "
            "then a colon.",
            "",
            "Do not paste that token here, or into any chat. It is the password "
            "to the whole bot. Say \"ready\" and I will tell you where it goes.",
            "",
        ]

    if "whatsapp" in wanted:
        lines += [
            "WhatsApp needs a Meta Business account and a phone number verified "
            "for the WhatsApp Business API — a longer process, and one with a few "
            "places to go wrong. Say \"whatsapp\" and I will take you through it "
            "a step at a time.",
            "",
        ]

    return "\n".join(lines).rstrip()


# The closing line, and the whole reason it is a constant.
#
# It used to read "Anything not working, tell me here and I will get a person on
# it" — which sets the expectation, in the first message after payment, that the
# way problems get solved here is by fetching a human. That is not what is being
# sold. Nera builds agents that resolve things themselves, and the message a
# customer reads first is the one that teaches them what to expect from it.
#
# The escalation is still offered, because refusing to ever fetch a person is its
# own failure, and a customer who needs one should not have to fight for it. It is
# simply no longer the default.
CLOSING_LINE = (
    "Something not working or unclear? Ask me here and I will walk you through "
    "it — I will only bring in a person if it is something I genuinely cannot "
    "help with directly."
)
