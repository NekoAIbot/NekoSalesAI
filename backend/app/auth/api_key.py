"""Authenticating a customer's own integration.

Provisioning has issued API keys since the day it was written, and until now
nothing verified one. The key was generated, hashed, stored, shown to the
customer once — and then no route on the server would accept it. This module is
the missing half.

Two credentials, deliberately different, because they authorise different things:

``X-API-Key`` is a secret. It identifies the workspace and is checked against a
stored SHA-256 hash. It belongs in server-to-server calls and must never appear
in a web page.

``widget_token`` is not a secret and is not handled here (see
``app.api.v1.routes.widget``). It ends up in the page source of the customer's
own website, so it authorises starting a conversation and nothing else.

Conflating the two would be the mistake that matters: if the secret key were
what the browser widget carried, every visitor to every customer's site would
be able to read a credential that can reconfigure the workspace.

Both paths resolve a ``WorkspaceProfile``, and from it the organization and the
``ProductConfig`` that governs replies — so a customer's agent answers from a
customer's catalog, which is the guarantee ``app.products.resolver`` exists to
protect.
"""

from __future__ import annotations

import hmac

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.workspace_profile import PROVISION_READY, WorkspaceProfile
from app.payments.provisioning import API_KEY_PREFIX_LENGTH, hash_api_key

# Presented by server-to-server callers. Named for the header it arrives in so
# the error messages can say something actionable.
API_KEY_HEADER = "X-API-Key"


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        # Tells a compliant client how to authenticate rather than leaving it to
        # guess from a bare 401.
        headers={"WWW-Authenticate": API_KEY_HEADER},
    )


def workspace_from_api_key(
    x_api_key: str | None = Header(default=None, alias=API_KEY_HEADER),
    db: Session = Depends(get_db),
) -> WorkspaceProfile:
    """Resolve the workspace a secret API key belongs to.

    Rejects an unprovisioned workspace as firmly as a wrong key. A profile that
    is still pending has a config that intake may not have finished writing, and
    an agent answering from a half-written catalog is exactly the failure
    ``resolver`` refuses to allow.
    """
    if not x_api_key:
        raise _unauthorized(f"Send your workspace API key in the {API_KEY_HEADER} header.")

    # Narrowed by the stored prefix, then verified against the full hash.
    #
    # The prefix exists so the UI can show which key is which; using it here
    # makes the lookup a single indexed row read instead of a scan of every
    # provisioned workspace, which is what this would otherwise become on every
    # authenticated request. The prefix is not the credential — a matching
    # prefix with the wrong body still fails the comparison below.
    prefix = x_api_key[:API_KEY_PREFIX_LENGTH]
    presented = hash_api_key(x_api_key)

    candidates = db.execute(
        select(WorkspaceProfile).where(
            WorkspaceProfile.api_key_prefix == prefix,
            WorkspaceProfile.api_key_hash.is_not(None),
        )
    ).scalars().all()

    matched = None
    for profile in candidates:
        # Constant-time, so a near-miss cannot be distinguished from a far one
        # by how long the answer took.
        if hmac.compare_digest(profile.api_key_hash or "", presented):
            matched = profile
            break

    if matched is None:
        # Deliberately does not distinguish "no such key" from "revoked key".
        raise _unauthorized("That API key is not valid.")

    if matched.status != PROVISION_READY:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This workspace is still being set up. Its API key will work "
                "once provisioning finishes."
            ),
        )

    return matched
