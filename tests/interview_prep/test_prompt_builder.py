from job_hunter.interview_prep.extractor import JobPosting
from job_hunter.interview_prep.prompt_builder import build_prompt
from job_hunter.referrals import Connection


def _posting(**overrides):
    defaults = dict(
        title="Backend Engineer",
        company="Acme Corp",
        description_text="Build scalable systems with Python.",
        url="https://example.com/job/1",
    )
    defaults.update(overrides)
    return JobPosting(**defaults)


def test_build_prompt_includes_core_sections():
    prompt = build_prompt(_posting(), resume_text=None, referral=None)

    assert "interview questions" in prompt
    assert "brush up" in prompt
    assert "STAR-method" in prompt
    assert "Backend Engineer" in prompt
    assert "Build scalable systems with Python." in prompt


def test_build_prompt_grounds_star_answers_in_resume_when_present():
    prompt = build_prompt(_posting(), resume_text="5 years leading backend teams.", referral=None)

    assert "Draft STAR-method" in prompt
    assert "5 years leading backend teams." in prompt
    assert "do not invent a candidate history" not in prompt


def test_build_prompt_uses_frameworks_when_no_resume():
    prompt = build_prompt(_posting(), resume_text=None, referral=None)

    assert "frameworks" in prompt
    assert "do not invent a candidate history" in prompt


def test_build_prompt_includes_referral_when_present():
    referral = Connection(name="Jane Smith", company="Acme Corp", title="Staff Engineer")

    prompt = build_prompt(_posting(), resume_text=None, referral=referral)

    assert "Jane Smith" in prompt
    assert "Staff Engineer" in prompt


def test_build_prompt_omits_referral_section_when_absent():
    prompt = build_prompt(_posting(), resume_text=None, referral=None)

    assert "Referral Contact" not in prompt


def test_build_prompt_notes_sparse_description():
    posting = _posting(description_text="Short blurb.")

    prompt = build_prompt(posting, resume_text=None, referral=None)

    assert "Short blurb." in prompt
    assert "may be incomplete" in prompt


def test_build_prompt_omits_sparse_note_for_substantial_description():
    posting = _posting(description_text="A" * 500)

    prompt = build_prompt(posting, resume_text=None, referral=None)

    assert "may be incomplete" not in prompt
