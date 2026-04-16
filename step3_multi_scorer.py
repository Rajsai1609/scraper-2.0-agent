#!/usr/bin/env python3
"""
Step 3 — Multi-student job scorer.

Loads every student from Supabase, loads all USA jobs from the Supabase
`scraped_jobs` table (NOT SQLite), and scores each job against each
student's resume using all-MiniLM-L6-v2.  Results are upserted to
`student_job_scores` in Supabase.

Using Supabase as the job source guarantees that job_id values in
student_job_scores match scraped_jobs.id exactly, so the dashboard
JOIN works correctly.

Run after the scraper pipeline has synced jobs to Supabase:
    python step3_multi_scorer.py

Env vars required:
    SUPABASE_URL
    SUPABASE_SERVICE_KEY
"""
from __future__ import annotations

import json
import os
import sys
import time
from typing import Any

import numpy as np
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

_JOBS_PAGE_SIZE = 1000   # Supabase max rows per request
_UPSERT_BATCH   = 200    # rows per score upsert call
_UPSERT_DELAY   = 0.2    # seconds between upsert batches


# ---------------------------------------------------------------------------
# Supabase helpers
# ---------------------------------------------------------------------------

def _get_supabase():
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise EnvironmentError(
            "SUPABASE_URL and SUPABASE_SERVICE_KEY must be set."
        )
    try:
        from supabase import create_client
    except ImportError:
        raise ImportError("supabase not installed — run: pip install supabase")
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def load_students(client) -> list[dict[str, Any]]:
    """Return all student rows from Supabase."""
    result = (
        client.table("students")
        .select("id, name, resume_text, skills")
        .execute()
    )
    return result.data or []


def load_jobs_from_supabase(client) -> list[dict[str, Any]]:
    """
    Return all USA jobs from Supabase scraped_jobs.

    Fetches id, title, company, location, job_category, and skills —
    the columns that actually exist in the live table.  'description'
    is not stored; we build a scoring text from the available fields.
    Paginates in batches of 1000 to retrieve the full set.
    """
    all_jobs: list[dict[str, Any]] = []
    offset = 0

    while True:
        result = (
            client.table("scraped_jobs")
            .select("id, title, company, location, job_category, skills")
            .eq("is_usa_job", True)
            .range(offset, offset + _JOBS_PAGE_SIZE - 1)
            .execute()
        )
        batch = result.data or []
        all_jobs.extend(batch)
        print(f"    fetched {len(all_jobs)} jobs so far...", end="\r")
        if len(batch) < _JOBS_PAGE_SIZE:
            break
        offset += _JOBS_PAGE_SIZE

    print()  # newline after \r
    return all_jobs


def _job_text(job: dict[str, Any]) -> str:
    """Build a scoring text from available fields (no description column)."""
    parts = [
        job.get("title") or "",
        job.get("company") or "",
        job.get("job_category") or "",
        job.get("location") or "",
    ]
    return " ".join(p for p in parts if p)[:2000]


def upsert_scores_batch(client, rows: list[dict]) -> int:
    """Upsert a batch of score rows; returns number of rows upserted."""
    result = (
        client.table("student_job_scores")
        .upsert(rows, on_conflict="student_id,job_id")
        .execute()
    )
    return len(result.data) if result.data else 0


# ---------------------------------------------------------------------------
# Scoring utilities
# ---------------------------------------------------------------------------

def _load_model():
    try:
        from src.scoring.matcher import _get_model
        return _get_model()
    except Exception:
        from sentence_transformers import SentenceTransformer
        return SentenceTransformer("all-MiniLM-L6-v2")


def _jaccard(a: list[str], b: list[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def encode_texts(model, texts: list[str], batch_size: int = 32) -> np.ndarray:
    """Encode texts; returns (N, D) float32 unit-normalised array."""
    return model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )


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


def compute_scores_for_student(
    *,
    student: dict[str, Any],
    job_ids: list[str],
    job_descriptions: list[str],
    job_skills_list: list[list[str]],
    job_embeddings: np.ndarray,
    model,
) -> list[dict]:
    """Score all jobs against one student; returns rows for Supabase upsert."""
    resume_text   = (student.get("resume_text") or "")[:2000]
    resume_skills = _parse_skills(student.get("skills") or [])
    student_id    = student["id"]

    resume_emb = model.encode(
        [resume_text],
        convert_to_numpy=True,
        normalize_embeddings=True,
    )  # (1, D)

    semantic_scores = (job_embeddings @ resume_emb.T).squeeze()  # (N,)

    rows: list[dict] = []
    for job_id, job_skills, sem_score in zip(
        job_ids, job_skills_list, semantic_scores
    ):
        skill_score = _jaccard(job_skills, resume_skills)
        fit_score   = round(0.4 * skill_score + 0.6 * float(sem_score), 4)

        rows.append({
            "student_id":     student_id,
            "job_id":         job_id,     # Supabase ID — matches scraped_jobs.id
            "fit_score":      fit_score,
            "skill_score":    round(skill_score, 4),
            "semantic_score": round(float(sem_score), 4),
        })

    return rows


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run() -> None:
    print("=" * 60)
    print("MCT PathAI — Multi-Student Scorer")
    print("=" * 60)

    # 1. Connect + load students
    print("\n[1/4] Connecting to Supabase...")
    client = _get_supabase()
    students = load_students(client)
    if not students:
        print("  No students found. Run step1_ingest_resumes.py first.")
        sys.exit(0)
    print(f"  {len(students)} student(s): {[s['name'] for s in students]}")

    # 2. Load jobs from Supabase (not SQLite) — IDs must match scraped_jobs.id
    print("\n[2/4] Loading jobs from Supabase scraped_jobs...")
    jobs = load_jobs_from_supabase(client)
    if not jobs:
        print("  No jobs in scraped_jobs. Run the scraper pipeline first.")
        sys.exit(0)
    print(f"  {len(jobs)} USA jobs loaded from Supabase")

    job_ids          = [j["id"] for j in jobs]
    job_descriptions = [_job_text(j) for j in jobs]
    job_skills_list  = [_parse_skills(j.get("skills") or []) for j in jobs]

    # 3. Batch-encode all job descriptions once (shared across students)
    print("\n[3/4] Encoding job descriptions (all-MiniLM-L6-v2)...")
    model = _load_model()
    job_embeddings = encode_texts(model, job_descriptions, batch_size=32)
    print(f"  Encoded {job_embeddings.shape[0]} jobs (dim={job_embeddings.shape[1]})")

    # 4. Score each student and upsert
    print("\n[4/4] Scoring and upserting to Supabase...")
    total_upserted = 0
    t0 = time.perf_counter()

    for student in students:
        name = student.get("name", student["id"])
        print(f"\n  Student: {name}")

        score_rows = compute_scores_for_student(
            student=student,
            job_ids=job_ids,
            job_descriptions=job_descriptions,
            job_skills_list=job_skills_list,
            job_embeddings=job_embeddings,
            model=model,
        )
        score_rows.sort(key=lambda r: r["fit_score"], reverse=True)

        student_upserted = 0
        for i in range(0, len(score_rows), _UPSERT_BATCH):
            batch = score_rows[i : i + _UPSERT_BATCH]
            student_upserted += upsert_scores_batch(client, batch)
            if i + _UPSERT_BATCH < len(score_rows):
                time.sleep(_UPSERT_DELAY)

        top5    = score_rows[:5]
        top_str = ", ".join(f"{r['fit_score']:.3f}" for r in top5)
        print(f"    Upserted {student_upserted} scores  |  top-5: [{top_str}]")
        total_upserted += student_upserted

    elapsed = time.perf_counter() - t0
    print(f"\n{'=' * 60}")
    print(f"Done in {elapsed:.1f}s")
    print(f"Total upserted: {total_upserted} rows across {len(students)} student(s)")


if __name__ == "__main__":
    run()
