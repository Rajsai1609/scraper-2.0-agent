#!/usr/bin/env python3
"""
Auto-ingest new waitlist submissions into the student pipeline.

Runs as the first step of the daily pipeline. Checks the `waitlist` table
for rows where processed = FALSE, downloads each resume from Supabase
Storage, extracts text and skills, upserts the student record, scores all
jobs against the new student, marks the waitlist row as processed, and
sends a confirmation email.

Env vars required:
    SUPABASE_URL
    SUPABASE_SERVICE_KEY

Env vars optional (email notifications):
    SMTP_HOST        e.g. smtp.gmail.com
    SMTP_PORT        default 587
    SMTP_USER        sender email address
    SMTP_PASS        sender password / app password
    SMTP_FROM_NAME   default "MCT PathAI"
"""
from __future__ import annotations

import os
import sys
import smtplib
import tempfile
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

RESUMES_DIR = Path("data/student_resumes")

SMTP_HOST      = os.getenv("SMTP_HOST", "")
SMTP_PORT      = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER      = os.getenv("SMTP_USER", "")
SMTP_PASS      = os.getenv("SMTP_PASS", "")
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "MCT PathAI")


# ---------------------------------------------------------------------------
# Supabase client
# ---------------------------------------------------------------------------

def _get_client():
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise EnvironmentError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set.")
    try:
        from supabase import create_client
    except ImportError:
        raise ImportError("supabase not installed — run: pip install supabase")
    return create_client(SUPABASE_URL, SUPABASE_KEY)


# ---------------------------------------------------------------------------
# Waitlist helpers
# ---------------------------------------------------------------------------

def fetch_pending(client) -> list[dict[str, Any]]:
    """Return waitlist rows that have a resume_url but are not yet processed."""
    result = (
        client.table("waitlist")
        .select("id, name, email, visa_status, target_role, resume_url")
        .eq("processed", False)
        .not_.is_("resume_url", "null")
        .execute()
    )
    return result.data or []


def mark_processed(client, waitlist_id: str) -> None:
    client.table("waitlist").update({
        "processed":    True,
        "processed_at": datetime.now(tz=timezone.utc).isoformat(),
    }).eq("id", waitlist_id).execute()


# ---------------------------------------------------------------------------
# Resume download
# ---------------------------------------------------------------------------

def download_resume(resume_url: str, dest: Path) -> Path:
    """
    Download the resume from the public Supabase Storage URL.
    Detect extension from URL; default to .pdf.
    Returns the local file path.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)

    url_path = resume_url.split("?")[0]          # strip query params
    ext = Path(url_path).suffix.lower() or ".pdf"
    local_path = dest.with_suffix(ext)

    resp = requests.get(resume_url, timeout=30)
    resp.raise_for_status()
    local_path.write_bytes(resp.content)
    return local_path


# ---------------------------------------------------------------------------
# Text + skill extraction  (reuse step1 logic)
# ---------------------------------------------------------------------------

def extract_text(path: Path) -> str:
    from step1_ingest_resumes import extract_text as _extract
    return _extract(path)


def extract_skills(text: str) -> list[str]:
    from step1_ingest_resumes import extract_skills as _skills
    return _skills(text)


# ---------------------------------------------------------------------------
# Student upsert  (reuse step1 upsert, keyed on filename = "waitlist_{email}")
# ---------------------------------------------------------------------------

def upsert_student(client, *, name: str, email: str,
                   resume_text: str, skills: list[str]) -> dict:
    from step1_ingest_resumes import upsert_student as _upsert
    filename = f"waitlist_{email.lower().replace('@', '_at_')}"
    return _upsert(
        client,
        name=name,
        filename=filename,
        resume_text=resume_text,
        skills=skills,
    )


# ---------------------------------------------------------------------------
# Score new student against all jobs
# ---------------------------------------------------------------------------

def score_student(client, student: dict) -> int:
    """
    Score all Supabase jobs against one student and upsert results.
    Reuses step3_multi_scorer functions to avoid duplicating model-load logic.
    Returns number of rows upserted.
    """
    import numpy as np
    from step3_multi_scorer import (
        load_jobs_from_supabase,
        encode_texts,
        compute_scores_for_student,
        upsert_scores_batch,
        _load_model,
        _job_text,
        _parse_skills,
        _UPSERT_BATCH,
        _UPSERT_DELAY,
    )
    import time

    jobs = load_jobs_from_supabase(client)
    if not jobs:
        print("    No jobs in scraped_jobs — skipping scoring.")
        return 0

    job_ids          = [j["id"] for j in jobs]
    job_descriptions = [_job_text(j) for j in jobs]
    job_skills_list  = [_parse_skills(j.get("skills") or []) for j in jobs]

    print(f"    Encoding {len(jobs)} job descriptions…")
    model = _load_model()
    job_embeddings = encode_texts(model, job_descriptions, batch_size=32)

    score_rows = compute_scores_for_student(
        student=student,
        job_ids=job_ids,
        job_descriptions=job_descriptions,
        job_skills_list=job_skills_list,
        job_embeddings=job_embeddings,
        model=model,
    )
    score_rows.sort(key=lambda r: r["fit_score"], reverse=True)

    upserted = 0
    for i in range(0, len(score_rows), _UPSERT_BATCH):
        batch = score_rows[i : i + _UPSERT_BATCH]
        upserted += upsert_scores_batch(client, batch)
        if i + _UPSERT_BATCH < len(score_rows):
            time.sleep(_UPSERT_DELAY)

    return upserted


# ---------------------------------------------------------------------------
# Email confirmation
# ---------------------------------------------------------------------------

def _send_email(to_email: str, subject: str, body: str) -> bool:
    """Low-level SMTP send. Returns True on success."""
    if not all([SMTP_HOST, SMTP_USER, SMTP_PASS]):
        print("    SMTP not configured — skipping email.")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"{SMTP_FROM_NAME} <{SMTP_USER}>"
    msg["To"]      = to_email
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, to_email, msg.as_string())
        return True
    except Exception as exc:
        print(f"    Email failed: {exc}")
        return False


def send_confirmation(to_email: str, to_name: str) -> bool:
    """Email sent when the student is fully ingested and dashboard is live."""
    subject = "You're in! Your MCT PathAI dashboard is live 🎯"
    body = f"""\
Hi {to_name},

Great news — your resume has been processed and your personalised \
job dashboard is now live!

View your matches at: https://mctpathai.com

Your top opportunities are ranked by AI match score, all \
pre-filtered for your visa status.

Reach out any time at connect@theteammc.com if you have questions.

— The MCT PathAI Team
Powered by MCTechnology LLC
"""
    return _send_email(to_email, subject, body)


def send_waitlisted(to_email: str, to_name: str) -> bool:
    """Email sent when the beta is full and the student stays on the waitlist."""
    subject = "You're on the MCT PathAI waitlist!"
    body = f"""\
Hi {to_name},

Thanks for signing up for MCT PathAI!

We've received your resume and you're on our waitlist. \
Our beta is currently at capacity (20 students), but we'll \
notify you as soon as your spot opens up.

In the meantime, follow us on LinkedIn for updates:
https://www.linkedin.com/company/106539005/

Questions? Reach us at connect@theteammc.com.

— The MCT PathAI Team
Powered by MCTechnology LLC
"""
    return _send_email(to_email, subject, body)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run() -> None:
    print("=" * 60)
    print("MCT PathAI — Auto-Ingest Waitlist")
    print("=" * 60)

    client = _get_client()

    # ── Beta limit check ─────────────────────────────────────────────────────
    BETA_LIMIT = 20
    count_res  = client.table("students").select("id", count="exact").execute()
    current_count = count_res.count or 0

    if current_count >= BETA_LIMIT:
        print(f"\nBeta full — {current_count}/{BETA_LIMIT} students.")
        print("New signups stay in waitlist until limit increases.")
        return

    slots_remaining = BETA_LIMIT - current_count
    print(f"\nBeta slots remaining: {slots_remaining}/{BETA_LIMIT}")

    pending = fetch_pending(client)
    if not pending:
        print("No new waitlist submissions to process. ✓")
        return

    # Send waitlisted email to any submissions that exceed the slot count
    if len(pending) > slots_remaining:
        overflow = pending[slots_remaining:]
        pending  = pending[:slots_remaining]
        print(f"{len(overflow)} submission(s) exceed remaining slots — notifying them.")
        for entry in overflow:
            sent = send_waitlisted(entry["email"], entry["name"])
            print(f"  Waitlist email {'sent ✓' if sent else 'skipped'} → {entry['name']}")

    print(f"\n{len(pending)} submission(s) to ingest.\n")

    success = failed = 0

    for entry in pending:
        name       = entry["name"]
        email      = entry["email"]
        resume_url = entry["resume_url"]
        wid        = entry["id"]

        print(f"Processing: {name} <{email}>")

        try:
            # 1 — Download resume
            safe_name = name.lower().replace(" ", "_")
            dest      = RESUMES_DIR / safe_name
            print(f"  [1/5] Downloading resume…")
            local_path = download_resume(resume_url, dest)
            print(f"        Saved to {local_path}")

            # 2 — Extract text + skills
            print(f"  [2/5] Extracting text…")
            text = extract_text(local_path)
            if not text.strip():
                raise ValueError("Empty text extracted from resume.")
            skills = extract_skills(text)
            print(f"        {len(text)} chars, {len(skills)} skills detected")

            # 3 — Upsert student
            print(f"  [3/5] Upserting student record…")
            record = upsert_student(
                client,
                name=name,
                email=email,
                resume_text=text,
                skills=skills,
            )
            student_id = record.get("id", "unknown")
            print(f"        student_id={student_id}")

            # Build student dict for scorer
            student_dict = {
                "id":          student_id,
                "name":        name,
                "resume_text": text,
                "skills":      skills,
            }

            # 4 — Score against all jobs
            print(f"  [4/5] Scoring jobs…")
            n_scored = score_student(client, student_dict)
            print(f"        {n_scored} score rows upserted")

            # 5 — Mark processed + send email
            print(f"  [5/5] Marking processed…")
            mark_processed(client, wid)
            sent = send_confirmation(email, name)
            print(f"        Email {'sent ✓' if sent else 'skipped'}")

            print(f"  ✅ {name} ingested successfully.\n")
            success += 1

        except Exception as exc:
            print(f"  ❌ Failed: {exc}\n")
            failed += 1
            # Don't mark processed so it retries next run

    print("=" * 60)
    print(f"Done. {success} ingested, {failed} failed.")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    run()
