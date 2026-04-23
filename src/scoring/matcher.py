from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Optional

from src.config.role_tracks import ROLE_TRACKS
from src.core.models import Job, Resume

if TYPE_CHECKING:
    import numpy as np
    from sentence_transformers import SentenceTransformer  # type: ignore

_model: Optional["SentenceTransformer"] = None


def _get_model() -> "SentenceTransformer":
    """Return the shared SentenceTransformer instance, loading it once."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer  # type: ignore

        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def _jaccard(a: list[str], b: list[str]) -> float:
    """Jaccard similarity between two skill lists."""
    set_a, set_b = set(a), set(b)
    if not set_a and not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def _parse_skills(raw: Any) -> list[str]:
    """Accept either a Python list (from Supabase JSONB) or a JSON string."""
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []
    return []


# ---------------------------------------------------------------------------
# Domain-aware scoring
# ---------------------------------------------------------------------------

# Keywords that signal a student is in a particular job domain.
# Checked against lowercase resume_text + skills joined as a string.
_DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "sap":           ["sap", "s/4hana", "hana", "abap", "sap basis", "sap fi", "sap co",
                      "fico", "sap mm", "sap sd", "sap pp", "sap ewm", "bw/4hana"],
    "bi":            ["bi analyst", "business intelligence", "bi developer", "tableau",
                      "power bi", "qlik", "looker", "microstrategy", "cognos",
                      "data visualization"],
    "data_engineer": ["data engineer", "data engineering", "etl", "data pipeline",
                      "apache airflow", "apache spark", "databricks", "kafka", "dbt",
                      "data warehouse"],
    "data_analyst":  ["data analyst", "data analysis", "sql analyst", "analytics analyst"],
    "java":          ["java developer", "java engineer", "spring boot", "j2ee", "hibernate"],
    "python_dev":    ["python developer", "python engineer", "django", "fastapi"],
    "react":         ["react developer", "frontend developer", "react engineer",
                      "vue developer", "angular developer", "ui developer"],
    "devops":        ["devops engineer", "cloud engineer", "site reliability", "sre",
                      "platform engineer", "infrastructure engineer", "devsecops"],
    "ml":            ["machine learning", "ml engineer", "data scientist", "mlops",
                      "deep learning", "ai engineer"],
}

# When a student is locked into a source domain, jobs in these domains get penalized.
_DOMAIN_CONFLICTS: dict[str, list[str]] = {
    "sap":   ["java", "python_dev", "react", "devops"],
    "bi":    ["devops", "java", "react"],
    "react": ["sap", "devops"],
}

_TITLE_BOOST    = 0.15
_DOMAIN_PENALTY = 0.20


def _detect_student_domain(resume_text: str, skills: list[str]) -> str | None:
    """
    Return the dominant job domain if one clearly outweighs all others.
    'Dominant' = top domain has ≥3× the keyword hits of the second-best domain.
    Returns None when the student appears multi-domain or domain is ambiguous.
    """
    combined = (resume_text + " " + " ".join(skills)).lower()
    counts: dict[str, int] = {
        domain: sum(1 for kw in keywords if kw in combined)
        for domain, keywords in _DOMAIN_KEYWORDS.items()
    }
    counts = {d: c for d, c in counts.items() if c > 0}
    if not counts:
        return None
    ranked = sorted(counts.items(), key=lambda x: x[1], reverse=True)
    top_domain, top_hits = ranked[0]
    if len(ranked) == 1 or top_hits >= 3 * ranked[1][1]:
        return top_domain
    return None


def _job_domain(job_title: str, job_skills: list[str]) -> str | None:
    """Return the domain of a job from its title and skill list, or None."""
    combined = (job_title + " " + " ".join(job_skills)).lower()
    for domain, keywords in _DOMAIN_KEYWORDS.items():
        if any(kw in combined for kw in keywords):
            return domain
    return None


def _title_matches_student(job_title: str, student_domain: str | None) -> bool:
    """True when the job title contains a keyword from the student's target domain."""
    if not student_domain:
        return False
    jt = job_title.lower()
    return any(kw in jt for kw in _DOMAIN_KEYWORDS.get(student_domain, []))


def encode_texts(model: Any, texts: list[str], batch_size: int = 32) -> Any:
    """Encode texts; returns (N, D) float32 unit-normalised array."""
    return model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )


def compute_scores_for_student(
    *,
    student: dict[str, Any],
    job_ids: list[str],
    job_titles: list[str],
    job_descriptions: list[str],
    job_skills_list: list[list[str]],
    job_embeddings: Any,
    model: Any,
) -> list[dict]:
    """Score all jobs against one student; returns rows for Supabase upsert."""
    resume_text    = (student.get("resume_text") or "")[:2000]
    resume_skills  = _parse_skills(student.get("skills") or [])
    student_id     = student["id"]
    student_domain = _detect_student_domain(resume_text, resume_skills)

    # Multi-track boosting — union keywords/titles from all selected tracks.
    # Prefer role_tracks array; fall back to single role_track string.
    raw_tracks: list[str] = student.get("role_tracks") or []
    if not raw_tracks:
        single = student.get("role_track") or "general"
        if single != "general":
            raw_tracks = [single]

    track_titles: list[str] = []
    track_kws:    list[str] = []
    max_t_boost = 0.0
    max_k_boost = 0.0
    for tn in raw_tracks:
        cfg = ROLE_TRACKS.get(tn, {})
        track_titles.extend(t.lower() for t in cfg.get("job_titles", []))
        track_kws.extend(k.lower() for k in cfg.get("keywords", []))
        max_t_boost = max(max_t_boost, cfg.get("title_boost", 0.0))
        max_k_boost = max(max_k_boost, cfg.get("keyword_boost", 0.0))

    resume_emb = model.encode(
        [resume_text],
        convert_to_numpy=True,
        normalize_embeddings=True,
    )  # (1, D)

    semantic_scores = (job_embeddings @ resume_emb.T).squeeze()  # (N,)

    rows: list[dict] = []
    for job_id, job_title, job_skills, sem_score in zip(
        job_ids, job_titles, job_skills_list, semantic_scores
    ):
        skill_score = _jaccard(job_skills, resume_skills)
        base_score  = 0.4 * skill_score + 0.6 * float(sem_score)

        # Title-aware boost: job title matches student's target domain
        if _title_matches_student(job_title, student_domain):
            base_score += _TITLE_BOOST

        # Domain penalty: completely wrong domain for this student
        job_dom = _job_domain(job_title, job_skills)
        if student_domain and job_dom in _DOMAIN_CONFLICTS.get(student_domain, []):
            base_score -= _DOMAIN_PENALTY

        # Role track boost — title match (any of the student's tracks)
        if track_titles and any(t in job_title.lower() for t in track_titles):
            base_score += max_t_boost

        # Role track boost — keyword density across all tracks (≥3 hits)
        if track_kws:
            job_combined = (job_title + " " + " ".join(job_skills)).lower()
            kw_hits = sum(1 for k in track_kws if k in job_combined)
            if kw_hits >= 3:
                base_score += max_k_boost

        fit_score = round(min(1.0, max(0.0, base_score)), 4)

        rows.append({
            "student_id":     student_id,
            "job_id":         job_id,
            "fit_score":      fit_score,
            "skill_score":    round(skill_score, 4),
            "semantic_score": round(float(sem_score), 4),
        })

    return rows


# ---------------------------------------------------------------------------
# Single-resume helpers (used by src/cli.py)
# ---------------------------------------------------------------------------

def score_job(job: Job, resume: Resume) -> float:
    """
    Return a match score in [0, 1] based on skill overlap.

    Falls back to 0.0 if neither side has skills.
    Uses sentence-transformers for semantic similarity when available.
    """
    skill_score = _jaccard(job.skills, resume.skills)

    semantic_score: Optional[float] = None
    if job.description and resume.raw_text:
        try:
            from sentence_transformers import util  # type: ignore

            model = _get_model()
            embeddings = model.encode(
                [job.description[:2000], resume.raw_text[:2000]],
                convert_to_tensor=True,
            )
            semantic_score = float(util.cos_sim(embeddings[0], embeddings[1]))
        except Exception:
            pass

    if semantic_score is not None:
        return round(0.4 * skill_score + 0.6 * semantic_score, 4)

    return round(skill_score, 4)


def score_all(jobs: list[Job], resume: Resume) -> list[Job]:
    """Return jobs with fit_score populated, sorted descending."""
    scored = [
        job.model_copy(update={"fit_score": score_job(job, resume)})
        for job in jobs
    ]
    return sorted(scored, key=lambda j: j.fit_score or 0, reverse=True)
