from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from src.core.models import Job, Resume

if TYPE_CHECKING:
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


def score_job(job: Job, resume: Resume) -> float:
    """
    Return a match score in [0, 1] based on skill overlap.

    Falls back to 0.0 if neither side has skills.
    Uses sentence-transformers for semantic similarity when available.
    """
    skill_score = _jaccard(job.skills, resume.skills)

    # Attempt semantic similarity if description is available
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
