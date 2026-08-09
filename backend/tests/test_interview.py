"""Conversational intake: a customer answers questions and gets an IntakeIn."""

from decimal import Decimal

import pytest

from app.products.interview import (
    STEP_AGENT_NAME,
    STEP_CAPABILITIES,
    STEP_COMPANY_NAME,
    STEP_DESCRIPTION,
    STEP_DISCOUNT,
    STEP_FAQS,
    STEP_PLANS,
    STEP_SUPPORT_EMAIL,
    InterviewError,
    next_question,
    parse,
)


def test_first_question_is_company_name():
    assert next_question({}).key == STEP_COMPANY_NAME


def test_answered_company_advances_to_next_question():
    assert next_question({STEP_COMPANY_NAME: "Bright Dental"}).key == STEP_DESCRIPTION


def test_thousands_separator_is_rejected_not_guessed():
    """The comma is the field separator, so '18,500' is genuinely ambiguous.

    Reading it as 500 would quote a price the customer never typed.
    """
    with pytest.raises(InterviewError, match="more than one number"):
        parse({
            STEP_COMPANY_NAME: "Clinic",
            STEP_PLANS: "Clean, 18,500, visit"
        })


def test_parse_with_only_company_name_builds_minimal_intake():
    intake = parse({STEP_COMPANY_NAME: "Bright Dental"})
    assert intake.company_name == "Bright Dental"
    assert intake.plans == ()
    assert intake.capabilities == ()


def test_plan_line_with_name_price_period_parses():
    intake = parse({
        STEP_COMPANY_NAME: "Clinic",
        STEP_PLANS: "Scale and Polish, 18500, visit"
    })
    assert len(intake.plans) == 1
    plan = intake.plans[0]
    assert plan.name == "Scale and Polish"
    assert plan.amount == Decimal("18500")
    assert plan.billing_period == "visit"
    assert plan.code == "scale_and_polish"


def test_money_with_decimals_parses():
    intake = parse({
        STEP_COMPANY_NAME: "Clinic",
        STEP_PLANS: "Clean, 18500.50, visit"
    })
    assert intake.plans[0].amount == Decimal("18500.50")


def test_currency_symbol_sets_the_currency():
    intake = parse({
        STEP_COMPANY_NAME: "Clinic",
        STEP_PLANS: "Clean, ₦18500, visit"
    })
    assert intake.plans[0].currency == "NGN"

    intake = parse({
        STEP_COMPANY_NAME: "Clinic",
        STEP_PLANS: "Clean, $100, month"
    })
    assert intake.plans[0].currency == "USD"


def test_currency_code_sets_the_currency():
    intake = parse({
        STEP_COMPANY_NAME: "Clinic",
        STEP_PLANS: "Clean, USD 100, month"
    })
    assert intake.plans[0].currency == "USD"


def test_first_plan_currency_carries_to_next():
    intake = parse({
        STEP_COMPANY_NAME: "Clinic",
        STEP_PLANS: "A, $100, month\nB, 200, month"
    })
    assert intake.plans[0].currency == "USD"
    assert intake.plans[1].currency == "USD"


def test_plan_without_price_raises():
    with pytest.raises(InterviewError, match="could not find a price"):
        parse({
            STEP_COMPANY_NAME: "Clinic",
            STEP_PLANS: "Clean, visit"
        })


def test_plan_without_period_raises():
    with pytest.raises(InterviewError, match="billing period"):
        parse({
            STEP_COMPANY_NAME: "Clinic",
            STEP_PLANS: "Clean, 18500"
        })


def test_plan_without_name_raises():
    with pytest.raises(InterviewError, match="needs a name"):
        parse({
            STEP_COMPANY_NAME: "Clinic",
            STEP_PLANS: ", 18500, visit"
        })


def test_capabilities_parse_one_per_line():
    intake = parse({
        STEP_COMPANY_NAME: "Clinic",
        STEP_CAPABILITIES: "Same-week appointments\nEvening slots"
    })
    assert len(intake.capabilities) == 2
    assert intake.capabilities[0] == "Same-week appointments"


def test_faq_with_question_mark_separator_parses():
    intake = parse({
        STEP_COMPANY_NAME: "Clinic",
        STEP_FAQS: "Do you take walk-ins? Yes, 9-5 daily."
    })
    assert len(intake.faqs) == 1
    assert intake.faqs[0].question == "Do you take walk-ins"
    assert intake.faqs[0].answer == "Yes, 9-5 daily."


def test_faq_without_question_mark_raises():
    with pytest.raises(InterviewError, match="question and an answer"):
        parse({
            STEP_COMPANY_NAME: "Clinic",
            STEP_FAQS: "Walk-ins yes"
        })


def test_discount_as_integer_parses():
    intake = parse({
        STEP_COMPANY_NAME: "Clinic",
        STEP_DISCOUNT: "10"
    })
    assert intake.max_auto_discount_percent == 10


def test_discount_non_integer_raises():
    with pytest.raises(InterviewError, match="whole number"):
        parse({
            STEP_COMPANY_NAME: "Clinic",
            STEP_DISCOUNT: "10.5"
        })


def test_skip_answers_are_ignored():
    intake = parse({
        STEP_COMPANY_NAME: "Clinic",
        STEP_PLANS: "none",
        STEP_CAPABILITIES: "-\nSkip\n",
        STEP_FAQS: "n/a",
    })
    assert intake.plans == ()
    assert intake.capabilities == ()
    assert intake.faqs == ()


def test_blank_lines_are_ignored():
    intake = parse({
        STEP_COMPANY_NAME: "Clinic",
        STEP_PLANS: "\n\nClean, 100, visit\n\n",
    })
    assert len(intake.plans) == 1


def test_optional_fields_default_when_absent():
    intake = parse({STEP_COMPANY_NAME: "Clinic"})
    assert intake.description == ""
    assert intake.agent_name == ""
    assert intake.support_email == ""
    assert intake.max_auto_discount_percent == 0


def test_all_fields_present():
    intake = parse({
        STEP_COMPANY_NAME: "Bright Dental",
        STEP_DESCRIPTION: "Same-week appointments.",
        STEP_AGENT_NAME: "Tolu from Bright Dental",
        STEP_SUPPORT_EMAIL: "care@bright.ng",
        STEP_PLANS: "Clean, 18500, visit",
        STEP_CAPABILITIES: "Evening slots",
        STEP_FAQS: "Walk-ins? Yes.",
        STEP_DISCOUNT: "10",
    })
    assert intake.company_name == "Bright Dental"
    assert intake.description == "Same-week appointments."
    assert intake.agent_name == "Tolu from Bright Dental"
    assert intake.support_email == "care@bright.ng"
    assert len(intake.plans) == 1
    assert len(intake.capabilities) == 1
    assert len(intake.faqs) == 1
    assert intake.max_auto_discount_percent == 10


# --- The interview over HTTP -------------------------------------------------


def test_interview_first_step_asks_for_company_name(client, auth_headers):
    response = client.post(
        "/api/v1/product-config/interview",
        json={"answers": {}},
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["question"]["key"] == STEP_COMPANY_NAME
    assert body["complete"] is False


def test_interview_previews_the_config_without_saving(client, auth_headers, db):
    from app.products.resolver import resolve_config
    from app.models.user import User

    response = client.post(
        "/api/v1/product-config/interview",
        json={
            "answers": {
                STEP_COMPANY_NAME: "Bright Dental",
                STEP_PLANS: "Clean, 18500, visit",
            }
        },
        headers=auth_headers,
    )

    body = response.json()
    assert body["preview"]["company_name"] == "Bright Dental"
    assert body["preview"]["plans"][0]["amount_minor"] == 1_850_000

    # Nothing was persisted: the only way to publish is the PUT.
    user = db.query(User).filter(User.email == "founder@nekosales.ai").first()
    assert resolve_config(db, user.organization_id).company_name != "Bright Dental"


def test_interview_reasks_on_an_unparseable_price(client, auth_headers):
    response = client.post(
        "/api/v1/product-config/interview",
        json={
            "answers": {
                STEP_COMPANY_NAME: "Clinic",
                STEP_PLANS: "Clean, about 18500, visit",
            },
            "last_key": STEP_PLANS,
        },
        headers=auth_headers,
    )

    body = response.json()
    assert body["error"]
    assert body["question"]["key"] == STEP_PLANS
    # No config is offered while an answer is still unparsed.
    assert body["preview"] is None
    assert body["complete"] is False


def test_interview_completes_when_every_question_is_answered(client, auth_headers):
    answers = {
        STEP_COMPANY_NAME: "Bright Dental",
        STEP_DESCRIPTION: "Same-week appointments.",
        STEP_AGENT_NAME: "Tolu from Bright Dental",
        STEP_SUPPORT_EMAIL: "care@bright.ng",
        STEP_PLANS: "Clean, 18500, visit",
        STEP_CAPABILITIES: "Evening slots",
        STEP_FAQS: "Walk-ins? Yes.",
        STEP_DISCOUNT: "10",
    }

    response = client.post(
        "/api/v1/product-config/interview",
        json={"answers": answers},
        headers=auth_headers,
    )

    body = response.json()
    assert body["complete"] is True
    assert body["question"] is None
    assert body["preview"]["company_name"] == "Bright Dental"
    # Interview claims are declared, exactly like form claims.
    assert body["preview"]["capabilities"][0]["source"] == "declared"


def test_interview_requires_authentication(client):
    response = client.post(
        "/api/v1/product-config/interview", json={"answers": {}}
    )
    assert response.status_code in (401, 403)
