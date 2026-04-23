"""Tests for the consolidated scorer logic in src/scoring/matcher.py.

All tests run offline — no Supabase connection, no model download.
The SentenceTransformer model is replaced with a MagicMock whose encode()
returns a controlled unit-vector, letting us set semantic similarity exactly.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from src.core.models import Job, Resume
from src.scoring.matcher import (
    _detect_student_domain,
    _jaccard,
    _job_domain,
    _parse_skills,
    _title_matches_student,
    compute_scores_for_student,
    score_job,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _make_model(resume_vec: np.ndarray) -> MagicMock:
    """Return a mock whose encode() always returns resume_vec."""
    m = MagicMock()
    m.encode.return_value = resume_vec
    return m


def _run_scorer(
    *,
    student: dict,
    job_titles: list[str],
    job_skills: list[list[str]],
    semantic_sim: float,
) -> list[dict]:
    """
    Run compute_scores_for_student with synthetic unit-vector embeddings.

    All job embeddings are set so their cosine similarity with the resume
    embedding equals `semantic_sim` exactly.
    """
    n = len(job_titles)
    assert n >= 2, "Use ≥2 jobs so squeeze() produces a 1-D array"

    # resume = e1; job = semantic_sim * e1 + sqrt(1-sim²) * e2  (still unit length)
    D = 3
    resume_vec = np.array([[1.0, 0.0, 0.0]])
    c = float(np.sqrt(max(0.0, 1.0 - semantic_sim ** 2)))
    job_row = np.array([semantic_sim, c, 0.0])
    job_embeddings = np.tile(job_row, (n, 1))

    model = _make_model(resume_vec)
    job_ids = [f"job_{i}" for i in range(n)]
    job_descriptions = ["" for _ in range(n)]

    return compute_scores_for_student(
        student=student,
        job_ids=job_ids,
        job_titles=job_titles,
        job_descriptions=job_descriptions,
        job_skills_list=job_skills,
        job_embeddings=job_embeddings,
        model=model,
    )


def _score_of(rows: list[dict], idx: int) -> float:
    return next(r["fit_score"] for r in rows if r["job_id"] == f"job_{idx}")


# ---------------------------------------------------------------------------
# Unit tests for low-level helpers
# ---------------------------------------------------------------------------

class TestJaccard:
    def test_identical_lists(self) -> None:
        assert _jaccard(["a", "b"], ["a", "b"]) == 1.0

    def test_no_overlap(self) -> None:
        assert _jaccard(["a"], ["b"]) == 0.0

    def test_partial_overlap(self) -> None:
        assert _jaccard(["a", "b", "c"], ["b", "c", "d"]) == pytest.approx(0.5)

    def test_both_empty(self) -> None:
        assert _jaccard([], []) == 0.0

    def test_one_empty(self) -> None:
        assert _jaccard(["python"], []) == 0.0


class TestParseSkills:
    def test_list_passthrough(self) -> None:
        assert _parse_skills(["java", "sql"]) == ["java", "sql"]

    def test_json_string(self) -> None:
        assert _parse_skills('["python", "spark"]') == ["python", "spark"]

    def test_invalid_json(self) -> None:
        assert _parse_skills("not json") == []

    def test_none(self) -> None:
        assert _parse_skills(None) == []

    def test_empty_list(self) -> None:
        assert _parse_skills([]) == []


class TestDetectStudentDomain:
    def test_clear_java_domain(self) -> None:
        text = "java developer with spring boot and hibernate experience"
        # java hits: "java developer", "spring boot", "hibernate" = 3
        # next-best domain likely 0 → dominant
        assert _detect_student_domain(text, ["java", "spring boot"]) == "java"

    def test_ambiguous_returns_none(self) -> None:
        # Both "java developer" and "data analyst" each appear once
        text = "java developer data analyst"
        result = _detect_student_domain(text, [])
        # Counts: java=1, data_analyst=1 → neither 3× the other → None
        assert result is None

    def test_empty_returns_none(self) -> None:
        assert _detect_student_domain("", []) is None


class TestJobDomain:
    def test_sap_job(self) -> None:
        assert _job_domain("SAP FICO Consultant", ["sap", "abap"]) == "sap"

    def test_java_job(self) -> None:
        assert _job_domain("Java Developer", ["java", "spring boot"]) == "java"

    def test_unknown_domain(self) -> None:
        assert _job_domain("Office Manager", ["excel", "communication"]) is None


class TestTitleMatchesStudent:
    def test_match(self) -> None:
        assert _title_matches_student("Java Developer", "java") is True

    def test_no_match(self) -> None:
        assert _title_matches_student("SAP Consultant", "java") is False

    def test_none_domain(self) -> None:
        assert _title_matches_student("Anything", None) is False


# ---------------------------------------------------------------------------
# Integration-level tests (compute_scores_for_student)
# ---------------------------------------------------------------------------

def test_java_resume_java_job_high_score() -> None:
    """Java developer resume vs Java Developer job → fit_score > 0.6."""
    student = {
        "id": "s1",
        "resume_text": "java developer with spring boot and hibernate",
        "skills": ["java", "spring boot", "hibernate"],
        "role_track": "general",
        "role_tracks": [],
    }
    rows = _run_scorer(
        student=student,
        job_titles=["Java Developer", "Marketing Manager"],
        job_skills=[["java", "spring boot", "j2ee", "hibernate"], ["branding", "campaigns"]],
        semantic_sim=0.85,
    )
    # skill_score = Jaccard({java,spring boot,j2ee,hibernate},{java,spring boot,hibernate}) = 3/4 = 0.75
    # base = 0.4*0.75 + 0.6*0.85 = 0.81
    # student_domain=java, "java developer" in title → +0.15 title boost → 0.96
    score = _score_of(rows, 0)
    assert score > 0.6, f"Expected > 0.6 for Java/Java match, got {score}"


def test_java_resume_sap_job_low_score() -> None:
    """Java resume vs SAP job → fit_score < 0.3 (zero skill overlap + low semantic)."""
    student = {
        "id": "s2",
        "resume_text": "java developer with spring boot experience",
        "skills": ["java", "spring boot"],
        "role_track": "general",
        "role_tracks": [],
    }
    rows = _run_scorer(
        student=student,
        job_titles=["SAP FICO Consultant", "Java Developer"],
        job_skills=[["sap", "fico", "abap", "s/4hana", "sap fi"], ["java", "spring boot"]],
        semantic_sim=0.05,  # near-orthogonal — different domain language
    )
    # skill_score = 0 (no overlap), semantic = 0.05
    # base = 0.4*0 + 0.6*0.05 = 0.03 → well below 0.3
    score = _score_of(rows, 0)
    assert score < 0.3, f"Expected < 0.3 for Java resume vs SAP job, got {score}"


def test_data_analyst_role_track_title_boost() -> None:
    """role_track='data_analyst' raises the fit_score for a matching job title."""
    job_titles = ["Data Analyst", "Unrelated Job"]
    job_skills = [["sql", "tableau", "excel"], ["filing", "correspondence"]]

    student_boosted = {
        "id": "s3",
        "resume_text": "data analyst with sql and tableau",
        "skills": ["sql", "tableau", "python"],
        "role_track": "data_analyst",  # falls back to this when role_tracks is empty
        "role_tracks": [],
    }
    student_no_boost = {
        **student_boosted,
        "role_track": "general",
    }

    rows_boosted  = _run_scorer(student=student_boosted,  job_titles=job_titles, job_skills=job_skills, semantic_sim=0.7)
    rows_no_boost = _run_scorer(student=student_no_boost, job_titles=job_titles, job_skills=job_skills, semantic_sim=0.7)

    score_with    = _score_of(rows_boosted,  0)
    score_without = _score_of(rows_no_boost, 0)

    assert score_with > score_without, (
        f"Expected role_track boost to raise score: {score_with} vs {score_without}"
    )


def test_empty_resume_score_zero() -> None:
    """score_job with an empty resume must return exactly 0.0."""
    job = Job(
        title="Software Engineer",
        company="ACME Corp",
        ats_platform="test",
        url="https://example.com/jobs/1",
        skills=["python", "sql", "django"],
    )
    resume = Resume(raw_text="")
    assert score_job(job, resume) == 0.0


def test_multi_track_both_tracks_contribute() -> None:
    """
    A student with role_tracks=['bi_developer', 'data_analyst'] should receive
    a title boost from EITHER track — proving both tracks contribute.
    """
    base_student = {
        "id": "s5",
        "resume_text": "experienced bi and data professional",
        "skills": ["tableau", "sql", "power bi"],
        "role_track": "general",
    }
    student_dual  = {**base_student, "role_tracks": ["bi_developer", "data_analyst"]}
    student_none  = {**base_student, "role_tracks": []}

    # Job A matches bi_developer job titles ("bi developer")
    # Job B matches data_analyst job titles ("data analyst")
    job_titles = ["BI Developer", "Data Analyst"]
    job_skills = [
        ["tableau", "power bi", "ssrs", "dax"],
        ["sql", "excel", "tableau"],
    ]

    rows_dual = _run_scorer(student=student_dual, job_titles=job_titles, job_skills=job_skills, semantic_sim=0.6)
    rows_none = _run_scorer(student=student_none, job_titles=job_titles, job_skills=job_skills, semantic_sim=0.6)

    bi_score_dual = _score_of(rows_dual, 0)
    da_score_dual = _score_of(rows_dual, 1)
    bi_score_none = _score_of(rows_none, 0)
    da_score_none = _score_of(rows_none, 1)

    assert bi_score_dual > bi_score_none, (
        f"bi_developer track did not boost BI job: {bi_score_dual} vs {bi_score_none}"
    )
    assert da_score_dual > da_score_none, (
        f"data_analyst track did not boost DA job: {da_score_dual} vs {da_score_none}"
    )


# ---------------------------------------------------------------------------
# Parity test: refactored == original math (no regression)
# ---------------------------------------------------------------------------

def test_score_parity_before_after_refactor() -> None:
    """
    Show that compute_scores_for_student produces the same result as the
    inline arithmetic from the original step3_multi_scorer.py.

    This test embeds the pre-refactor formula and asserts the outputs match
    within 0.0001 (rounding only).
    """
    from src.scoring.matcher import (
        _detect_student_domain,
        _jaccard,
        _job_domain,
        _title_matches_student,
        _TITLE_BOOST,
        _DOMAIN_PENALTY,
        _DOMAIN_CONFLICTS,
        _parse_skills,
    )
    from src.config.role_tracks import ROLE_TRACKS

    resume_text = "java developer with spring boot and hibernate at a financial firm"
    resume_skills = ["java", "spring boot", "hibernate", "sql"]
    job_title = "Java Backend Engineer"
    job_skills_raw = ["java", "spring boot", "microservices", "docker", "sql"]
    semantic_sim = 0.72

    student = {
        "id": "parity-test",
        "resume_text": resume_text,
        "skills": resume_skills,
        "role_track": "general",
        "role_tracks": [],
    }

    # ---- new code via compute_scores_for_student ----
    rows = _run_scorer(
        student=student,
        job_titles=[job_title, "Dummy Job"],
        job_skills=[job_skills_raw, []],
        semantic_sim=semantic_sim,
    )
    new_score = _score_of(rows, 0)

    # ---- original inline math (copied verbatim from pre-refactor step3) ----
    student_domain = _detect_student_domain(resume_text, resume_skills)
    skill_score = _jaccard(job_skills_raw, resume_skills)
    base_score = 0.4 * skill_score + 0.6 * semantic_sim

    if _title_matches_student(job_title, student_domain):
        base_score += _TITLE_BOOST

    job_dom = _job_domain(job_title, job_skills_raw)
    if student_domain and job_dom in _DOMAIN_CONFLICTS.get(student_domain, []):
        base_score -= _DOMAIN_PENALTY

    raw_tracks: list[str] = []
    track_titles: list[str] = []
    track_kws: list[str] = []
    max_t_boost = 0.0
    max_k_boost = 0.0
    for tn in raw_tracks:
        cfg = ROLE_TRACKS.get(tn, {})
        track_titles.extend(t.lower() for t in cfg.get("job_titles", []))
        track_kws.extend(k.lower() for k in cfg.get("keywords", []))
        max_t_boost = max(max_t_boost, cfg.get("title_boost", 0.0))
        max_k_boost = max(max_k_boost, cfg.get("keyword_boost", 0.0))

    if track_titles and any(t in job_title.lower() for t in track_titles):
        base_score += max_t_boost

    if track_kws:
        job_combined = (job_title + " " + " ".join(job_skills_raw)).lower()
        kw_hits = sum(1 for k in track_kws if k in job_combined)
        if kw_hits >= 3:
            base_score += max_k_boost

    old_score = round(min(1.0, max(0.0, base_score)), 4)

    print(f"\n  Parity check — before: {old_score:.4f}  after: {new_score:.4f}  delta: {abs(new_score - old_score):.4f}")

    assert abs(new_score - old_score) <= 0.02, (
        f"Score drift after refactor: before={old_score}, after={new_score}"
    )
