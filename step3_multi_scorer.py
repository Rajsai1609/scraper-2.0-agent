#!/usr/bin/env python3
"""
Step 3 — Multi-student job scorer.

Loads every student from Supabase, loads all jobs from SQLite, and scores
each job against each student's resume using all-MiniLM-L6-v2 (the same
model the existing single-student scorer uses).  Results are upserted to
`student_job_scores` in Supabase.

Run in CI *after* the single-student scorer step:
    python step3_multi_scorer.py

Env vars required:
    SUPABASE_URL
    SUPABASE_SERVICE_KEY

Performance notes:
  - Job descriptions are batch-encoded once (shared across all students).
  - Per-student cost is: 1 encode call + 1 vectorised cosine-similarity.
  - 5 students × 5000 jobs ≈ 2 min on CPU (dominated by job encoding).
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
SQLITE_PATH = Path(os.getenv("SQLITE_PATH", "data/jobs.db"))

# Supabase batch upsert size — keep well under the 1 MB request limit
_UPSERT_BATCH = 200
# Pause between batches to avoid Supabase rate limits
_UPSERT_DELAY = 0.2


# ---------------------------------------------------------------------------
# Supabase helpers
# ---------------------------------------------------------------------------

def _get_supabase():
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise EnvironmentError(
            "SUPABASE_URL and SUPABASE_SERVICE_KEY must be set."
        )
    try:
        from supabase import create_client  # type: ignore[import]
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


def upsert_scores_batch(client, rows: list[dict]) -> int:
    """Upsert a batch of score rows; returns number of rows upserted."""
    result = (
        client.table("student_job_scores")
        .upsert(rows, on_conflict="student_id,job_id")
        .execute()
    )
    return len(result.data) if result.data else 0


# ---------------------------------------------------------------------------
# SQLite helpers
# ---------------------------------------------------------------------------

def load_jobs_from_sqlite() -> list[dict[str, Any]]:
    """Return all job rows as dicts from the local SQLite db."""
    import sqlite3

    if not SQLITE_PATH.exists():
        raise FileNotFoundError(f"SQLite database not found: {SQLITE_PATH}")

    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT id, description, skills FROM jobs"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Scoring utilities
# ---------------------------------------------------------------------------

def _load_model():
    """Return the cached SentenceTransformer model (all-MiniLM-L6-v2)."""
    # Reuse the singleton already defined in src/scoring/matcher.py
    try:
        from src.scoring.matcher import _get_model  # type: ignore[import]
        return _get_model()
    except Exception:
        # Fallback: load directly
        from sentence_transformers import SentenceTransformer  # type: ignore[import]
        return SentenceTransformer("all-MiniLM-L6-v2")


def _jaccard(a: list[str], b: list[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def encode_texts(model, texts: list[str], batch_size: int = 32) -> np.ndarray:
    """Encode a list of texts; returns (N, D) float32 array."""
    return model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=True,  # unit vectors → dot product == cosine sim
    )


def compute_scores_for_student(
    *,
    student: dict[str, Any],
    job_ids: list[str],
    job_descriptions: list[str],
    job_skills_list: list[list[str]],
    job_embeddings: np.ndarray,   # (N, D) pre-encoded, unit-normalised
    model,
) -> list[dict]:
    """
    Score all jobs against one student's resume.

    Returns a list of dicts ready for Supabase upsert.
    """
    resume_text = (student.get("resume_text") or "")[:2000]
    resume_skills: list[str] = student.get("skills") or []
    if isinstance(resume_skills, str):
        try:
            resume_skills = json.loads(resume_skills)
        except Exception:
            resume_skills = []

    student_id = student["id"]

    # Semantic embedding for this student's resume
    resume_emb = model.encode(
        [resume_text],
        convert_to_numpy=True,
        normalize_embeddings=True,
    )  # shape (1, D)

    # Cosine similarities: (N,) because embeddings are unit-normalised
    semantic_scores = (job_embeddings @ resume_emb.T).squeeze()  # (N,)

    rows: list[dict] = []
    for i, (job_id, job_skills, sem_score) in enumerate(
        zip(job_ids, job_skills_list, semantic_scores)
    ):
        skill_score = _jaccard(job_skills, resume_skills)
        fit_score = round(0.4 * skill_score + 0.6 * float(sem_score), 4)

        rows.append({
            "student_id":     student_id,
            "job_id":         job_id,
            "fit_score":      fit_score,
            "skill_score":    round(skill_score, 4),
            "semantic_score": round(float(sem_score), 4),
        })

    return rows


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run() -> None:
    print("="*60)
    print("MCT PathAI — Multi-Student Scorer")
    print("="*60)

    # 1. Connect + load students
    print("\n[1/4] Connecting to Supabase...")
    client = _get_supabase()
    students = load_students(client)
    if not students:
        print("  No students found in Supabase. Run step1_ingest_resumes.py first.")
        sys.exit(0)
    print(f"  {len(students)} student(s): {[s['name'] for s in students]}")

    # 2. Load jobs from SQLite
    print("\n[2/4] Loading jobs from SQLite...")
    jobs = load_jobs_from_sqlite()
    if not jobs:
        print("  No jobs in SQLite. Run the scraper first.")
        sys.exit(0)
    print(f"  {len(jobs)} jobs loaded")

    job_ids = [j["id"] for j in jobs]
    job_descriptions = [(j.get("description") or "")[:2000] for j in jobs]
    job_skills_list: list[list[str]] = []
    for j in jobs:
        raw = j.get("skills") or "[]"
        try:
            skills = json.loads(raw) if isinstance(raw, str) else raw
            job_skills_list.append(skills if isinstance(skills, list) else [])
        except Exception:
            job_skills_list.append([])

    # 3. Batch-encode all job descriptions (done once, shared across students)
    print("\n[3/4] Encoding job descriptions (all-MiniLM-L6-v2)...")
    model = _load_model()
    job_embeddings = encode_texts(model, job_descriptions, batch_size=32)
    print(f"  Encoded {job_embeddings.shape[0]} jobs  (dim={job_embeddings.shape[1]})")

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

        # Sort descending so top scores are visible in Supabase first
        score_rows.sort(key=lambda r: r["fit_score"], reverse=True)

        # Batch upsert
        student_upserted = 0
        for i in range(0, len(score_rows), _UPSERT_BATCH):
            batch = score_rows[i : i + _UPSERT_BATCH]
            upserted = upsert_scores_batch(client, batch)
            student_upserted += upserted
            if i + _UPSERT_BATCH < len(score_rows):
                time.sleep(_UPSERT_DELAY)

        top5 = score_rows[:5]
        top_str = ", ".join(f"{r['fit_score']:.3f}" for r in top5)
        print(f"    Upserted {student_upserted} scores  |  top-5: [{top_str}]")
        total_upserted += student_upserted

    elapsed = time.perf_counter() - t0
    print(f"\n{'='*60}")
    print(f"Done in {elapsed:.1f}s")
    print(f"Total upserted: {total_upserted} score rows across {len(students)} student(s)")


if __name__ == "__main__":
    run()
