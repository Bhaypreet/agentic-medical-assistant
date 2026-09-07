"""Red-flag escalation and model-emitted HTML.

Both found by testing the deployed app. Triage asks one clarifying
question before assessing severity, which is right for a sore throat and
wrong for crushing chest pain - the patient was answering "how long has
the pain been going on?" instead of being told to call an ambulance. And
the model writes `<br>` inside markdown tables, which reached the patient
as literal "<br>" mid-sentence.
"""

import pytest

from app.safety import apply_safety, looks_like_emergency, normalise_line_breaks

# --------------------------------------------------------- red flags


@pytest.mark.parametrize(
    "text",
    [
        "I have crushing chest pain radiating to my left arm, I am sweating and breathless",
        "chest pain that started an hour ago",
        "sudden chest tightness and I cannot breathe",
        "my face is drooping and my speech is slurred",
        "worst headache of my life, came on suddenly",
        "he is unconscious and unresponsive",
        "I am coughing blood",
        "she had a seizure ten minutes ago",
        "heavy bleeding that won't stop",
        "my throat is closing and my tongue is swelling",
        "I took an overdose of pills",
        "I want to die",
        "his lips are turning blue",
    ],
)
def test_red_flags_are_recognised(text):
    assert looks_like_emergency(text), text


@pytest.mark.parametrize(
    "text",
    [
        "I have a mild headache and a runny nose",
        "sore throat for two days",
        "my knee aches after running",
        "I have chest congestion from a cold",
        "mild indigestion after a heavy meal",
        "a small cut on my finger is bleeding",
        "what is hypertension?",
        "suggest a diet plan for high cholesterol",
        "",
    ],
)
def test_everyday_complaints_do_not_trigger(text):
    """A false positive tells someone with a head cold to call an
    ambulance, which is its own kind of harm."""

    assert not looks_like_emergency(text), text


# ------------------------------------------------- model-emitted HTML


def test_breaks_inside_a_table_row_become_spaces():
    """A markdown cell cannot hold a newline, so a space is the only
    thing that keeps the table intact."""

    row = "| Lifestyle | - Obesity<br>- Smoking<br>- Alcohol |"

    assert normalise_line_breaks(row) == "| Lifestyle | - Obesity - Smoking - Alcohol |"
    assert "<br>" not in normalise_line_breaks(row)


def test_breaks_outside_a_table_become_newlines():
    assert normalise_line_breaks("Line one<br>Line two") == "Line one\nLine two"


@pytest.mark.parametrize("tag", ["<br>", "<br/>", "<br />", "<BR>", "<Br />"])
def test_every_spelling_of_the_tag_is_handled(tag):
    assert "br" not in normalise_line_breaks(f"a{tag}b").lower().replace("\n", "")


def test_a_table_keeps_its_column_count():
    row = "| A | x<br>y | B |"
    assert normalise_line_breaks(row).count("|") == row.count("|")


def test_text_without_html_is_untouched():
    text = "## Assessment\n\n**Risk level:** Emergency\n\n- one\n- two"
    assert normalise_line_breaks(text) == text


def test_indentation_outside_tables_survives():
    text = "- parent\n    - nested item\n        - deeper"
    assert normalise_line_breaks(text) == text


def test_apply_safety_strips_breaks_and_escalates_together():
    out = apply_safety("| x | a<br>b |", severity=5, emergency=True)

    assert "<br>" not in out
    assert "Seek emergency care now" in out
    assert "does not replace advice" in out
