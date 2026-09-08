"""Configure a workspace's product — the factory's intake desk.

Every route here is authenticated and scoped to the caller's organization.
That scoping is the tenant boundary — a user must not be able to read or
rewrite another company's product config by guessing an organization id, so
the filter lives in the query rather than in a post-fetch check.

One deliberate asymmetry: there is no route for the storefront's own config.
NekoSalesAI's plans and verified claims live in ``app.catalog.products`` as
reviewable Python; a web form that could rewrite them would be a way to change
our prices without a diff.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.dependencies.database import get_db
from app.models.user import User
from app.products import interview
from app.products.interview import InterviewError
from app.products.intake import IntakeError, IntakeService
from app.schemas.intake import IntakeIn, InterviewIn
from app.schemas.intake_out import AgentOut, ConfigOut, InterviewOut, QuestionOut

router = APIRouter(
    prefix="/product-config",
    tags=["Product Config"],
)

# Which agent to read or write, for a workspace that holds more than one.
#
# Optional, and omitting it keeps the single-agent behaviour every existing
# caller relies on. It is not optional in effect for a customer who bought both
# products: without it the service resolves to whichever profile is oldest, so
# one of their two agents would be unreachable by any request they could make.
_ROLE = Query(
    default=None,
    max_length=40,
    description=(
        "Which agent in this workspace. Omit when there is only one. "
        "Get the valid values from GET /product-config/agents."
    ),
)


@router.get(
    "/agents",
    response_model=list[AgentOut],
)
def list_agents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Every agent this workspace holds.

    The first call a settings page makes, and the reason it can be correct for a
    customer who bought both products: the ``role`` strings to send back are
    published here rather than guessed. Reports ``configured`` per agent, which
    is false for everything freshly provisioned — that is the honest starting
    state and the whole reason this page exists.

    Declared above the bare ``""`` routes so ``/agents`` is not read as a path
    parameter of something else later.
    """
    service = IntakeService(db)

    return [
        AgentOut.from_profile(
            profile,
            service.current_config(current_user.organization_id, profile.role),
        )
        for profile in service.agents_for(current_user.organization_id)
    ]


@router.get(
    "",
    response_model=ConfigOut,
)
def get_config(
    role: str | None = _ROLE,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Read the caller's product config — what their agent will actually say."""
    return ConfigOut.from_config(
        IntakeService(db).current_config(current_user.organization_id, role)
    )


@router.put(
    "",
    response_model=ConfigOut,
)
def put_config(
    payload: IntakeIn,
    role: str | None = _ROLE,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Replace the caller's product config wholesale."""
    service = IntakeService(db)
    try:
        saved = service.save(
            current_user.organization_id, payload.to_config(), role
        )
    except IntakeError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    return ConfigOut.from_config(saved)


@router.post(
    "/interview",
    response_model=InterviewOut,
)
def interview_step(
    payload: InterviewIn,
    current_user: User = Depends(get_current_user),
):
    """Ask the next requirements question, given every answer so far.

    Stateless on purpose: the caller holds the draft. Nothing is saved here —
    a customer can back out of the interview without a half-configured product
    going live, and the only way to publish is the PUT above.
    """
    answers = dict(payload.answers)

    try:
        complete = interview.is_complete(answers)
        # next_question validates every answer already given, so an
        # unparseable price surfaces here rather than in the preview.
        question = None if complete else interview.next_question(answers)
        preview = _preview(answers)
    except (InterviewError, ValidationError) as exc:
        # A schema error and a parse error mean the same thing to a customer:
        # that answer needs another go. Re-ask rather than advancing, and
        # offer no preview — a half-understood answer must not look accepted.
        message = str(exc) if isinstance(exc, InterviewError) else _first_error(exc)
        asked = interview.QUESTION_BY_KEY.get(payload.last_key)
        return InterviewOut(
            question=_question_out(asked) if asked else None,
            error=message,
        )

    return InterviewOut(
        question=_question_out(question) if question else None,
        complete=complete,
        preview=preview,
    )


def _preview(answers: dict[str, str]) -> ConfigOut | None:
    """The config these answers would produce, or None if it is too early.

    Nothing here is saved. The preview exists so a customer can watch their
    product take shape before publishing it.
    """
    if not answers.get(interview.STEP_COMPANY_NAME, "").strip():
        return None
    return ConfigOut.from_config(interview.parse(answers).to_config())


def _question_out(question: interview.Question) -> QuestionOut:
    return QuestionOut(
        key=question.key,
        prompt=question.prompt,
        help_text=question.help_text,
        optional=question.optional,
        multiline=question.multiline,
    )


def _first_error(exc: ValidationError) -> str:
    """The first validation message, phrased for someone in a chat box."""
    errors = exc.errors()
    if not errors:  # pragma: no cover - ValidationError always carries one
        return "That answer did not work. Please try again."
    return errors[0].get("msg", "That answer did not work. Please try again.")
