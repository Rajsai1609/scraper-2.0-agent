#!/usr/bin/env python3
"""
Send personalized weekly insights emails to every student in MCT PathAI.

For each student in the `students` table:
  1. Fetch their top 10 job matches from student_job_scores JOIN scraped_jobs
  2. Compute match statistics (totals, grade breakdown, best company/category)
  3. Send a formatted plain-text insights email via SMTP

Run standalone or as the final step in daily-pipeline.yml.

Env vars required:
    SUPABASE_URL
    SUPABASE_SERVICE_KEY
    SMTP_HOST
    SMTP_USER
    SMTP_PASS

Env vars optional:
    SMTP_PORT        default 587
    SMTP_FROM_NAME   default "MCT PathAI"
    MIN_SCORE        default 0.25  — minimum fit_score to include in stats
    TOP_N_EMAIL      default 5     — number of top jobs shown in email body
"""
from __future__ import annotations

import os
import smtplib
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SUPABASE_URL   = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY   = os.getenv("SUPABASE_SERVICE_KEY", "")

SMTP_HOST      = os.getenv("SMTP_HOST", "")
SMTP_PORT      = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER      = os.getenv("SMTP_USER", "")
SMTP_PASS      = os.getenv("SMTP_PASS", "")
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "MCT PathAI")

MIN_SCORE   = float(os.getenv("MIN_SCORE", "0.25"))
TOP_N_EMAIL = int(os.getenv("TOP_N_EMAIL", "5"))

# Grade thresholds — must match lib/utils.ts scoreToGrade
_GRADE_THRESHOLDS: list[tuple[float, str]] = [
    (0.60, "A+"),
    (0.50, "A"),
    (0.40, "B+"),
    (0.30, "B"),
    (0.25, "C+"),
    (0.00, "C"),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _score_to_grade(score: float) -> str:
    for threshold, grade in _GRADE_THRESHOLDS:
        if score >= threshold:
            return grade
    return "F"


def _get_client():
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise EnvironmentError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set.")
    try:
        from supabase import create_client
    except ImportError:
        raise ImportError("supabase not installed — run: pip install supabase")
    return create_client(SUPABASE_URL, SUPABASE_KEY)


# ---------------------------------------------------------------------------
# Supabase queries
# ---------------------------------------------------------------------------

def fetch_all_students(client) -> list[dict[str, Any]]:
    """
    Return id, name, email for every student that has a processed waitlist row.

    students table has no email column — emails live in the waitlist table.
    We fetch both tables and join in Python on LOWER(TRIM(name)).
    Only students whose name matches a processed waitlist row (with an email)
    are included.
    """
    students_res = (
        client.table("students")
        .select("id, name")
        .order("name")
        .execute()
    )
    students = students_res.data or []

    waitlist_res = (
        client.table("waitlist")
        .select("name, email")
        .eq("processed", True)
        .not_.is_("email", "null")
        .execute()
    )
    # Build lookup: normalised_name -> email (last processed entry wins on collision)
    email_by_name: dict[str, str] = {
        row["name"].lower().strip(): row["email"]
        for row in (waitlist_res.data or [])
        if row.get("name") and row.get("email")
    }

    result: list[dict[str, Any]] = []
    for s in students:
        email = email_by_name.get(s["name"].lower().strip())
        if email:
            result.append({"id": s["id"], "name": s["name"], "email": email})

    return result


def fetch_top_jobs(client, student_id: str, limit: int = 10) -> list[dict[str, Any]]:
    """
    Return up to `limit` top-scoring job rows for a student.
    Each row is a flat dict with fit_score + scraped_jobs fields merged.
    """
    result = (
        client.table("student_job_scores")
        .select(
            "fit_score, "
            "scraped_jobs(id, title, company, url, location, job_category)"
        )
        .eq("student_id", student_id)
        .gte("fit_score", MIN_SCORE)
        .order("fit_score", desc=True)
        .limit(limit)
        .execute()
    )
    rows = result.data or []

    merged: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    seen_title_co: set[str] = set()

    for row in rows:
        job = row.get("scraped_jobs")
        if not job:
            continue

        url_key = (job.get("url") or "").lower().strip()
        title_key = (
            f"{(job.get('title') or '').lower().strip()}-"
            f"{(job.get('company') or '').lower().strip()}"
        )

        if url_key and url_key in seen_urls:
            continue
        if title_key in seen_title_co:
            continue

        if url_key:
            seen_urls.add(url_key)
        seen_title_co.add(title_key)

        merged.append({
            "title":        job.get("title", "Unknown Role"),
            "company":      job.get("company", "Unknown Company"),
            "url":          job.get("url", ""),
            "location":     job.get("location") or "Remote / Not specified",
            "job_category": job.get("job_category") or "General",
            "fit_score":    row["fit_score"],
            "fit_pct":      round(row["fit_score"] * 100),
            "grade":        _score_to_grade(row["fit_score"]),
        })

    return merged


def fetch_new_jobs_since_yesterday(client) -> int:
    """Count jobs posted since yesterday across all scraped_jobs."""
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    result = (
        client.table("scraped_jobs")
        .select("id", count="exact")
        .gte("date_posted", yesterday)
        .execute()
    )
    return result.count or 0


def fetch_total_match_count(client, student_id: str) -> int:
    """Count of all score rows at or above MIN_SCORE for this student."""
    result = (
        client.table("student_job_scores")
        .select("student_id", count="exact")
        .eq("student_id", student_id)
        .gte("fit_score", MIN_SCORE)
        .execute()
    )
    return result.count or 0


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def build_stats(top_jobs: list[dict[str, Any]], total_matches: int) -> dict[str, Any]:
    """Derive summary statistics from the student's top job list."""
    if not top_jobs:
        return {
            "total_matches":   total_matches,
            "top_score_pct":   0,
            "a_plus_count":    0,
            "a_count":         0,
            "best_company":    "N/A",
            "best_category":   "N/A",
            "top_grade":       "N/A",
        }

    top_score = top_jobs[0]["fit_score"]
    grade_counts: Counter[str] = Counter(j["grade"] for j in top_jobs)
    company_counts: Counter[str] = Counter(j["company"] for j in top_jobs)
    category_counts: Counter[str] = Counter(j["job_category"] for j in top_jobs)

    return {
        "total_matches": total_matches,
        "top_score_pct": round(top_score * 100),
        "a_plus_count":  grade_counts.get("A+", 0),
        "a_count":       grade_counts.get("A", 0),
        "best_company":  company_counts.most_common(1)[0][0],
        "best_category": category_counts.most_common(1)[0][0],
        "top_grade":     _score_to_grade(top_score),
    }


# ---------------------------------------------------------------------------
# Email body builder
# ---------------------------------------------------------------------------

def _action_advice(top_score: float) -> str:
    if top_score >= 0.65:
        return "Excellent matches! Apply to your top 5 today."
    if top_score >= 0.50:
        return "Strong matches! Focus on A+ and A grades."
    return (
        "Good start! Consider optimizing your resume with ResumeAI "
        "to improve scores."
    )


def build_email_body(
    name: str,
    stats: dict[str, Any],
    top_jobs: list[dict[str, Any]],
    new_jobs_count: int = 0,
) -> str:
    display_jobs = top_jobs[:TOP_N_EMAIL]
    top_score_raw = top_jobs[0]["fit_score"] if top_jobs else 0.0

    jobs_block_lines: list[str] = []
    for i, job in enumerate(display_jobs, start=1):
        jobs_block_lines.append(
            f"{i}. {job['title']} @ {job['company']}\n"
            f"   📍 {job['location']}\n"
            f"   🎯 Match Score: {job['fit_pct']}%\n"
            f"   🏅 Grade: {job['grade']}\n"
            f"   🔗 Apply: {job['url']}"
        )
    jobs_block = "\n\n".join(jobs_block_lines) if jobs_block_lines else "  No matches found yet."

    advice = _action_advice(top_score_raw)

    new_jobs_line = f"🆕 {new_jobs_count} new jobs since yesterday\n\n" if new_jobs_count > 0 else ""

    body = f"""\
Hi {name},

{new_jobs_line}Here's your personalized job search insights for this week!

📊 YOUR MATCH STATISTICS:
- Total matched jobs: {stats['total_matches']}
- Top match score: {stats['top_score_pct']}%
- A+ matches: {stats['a_plus_count']}
- A  matches: {stats['a_count']}
- Best matching company: {stats['best_company']}

🏆 YOUR TOP {len(display_jobs)} JOB MATCHES TODAY:

{jobs_block}

💡 INSIGHTS:
- Best job category for you: {stats['best_category']}
- Recommended action: {advice}

📈 IMPROVE YOUR MATCHES:
Visit mctpathai.com to see all your matches and generate tailored resumes per job.

Questions? Reply to this email or:
📱 +1 (206) 552-8424
💼 linkedin.com/company/106539005

- Rajsai
MCTechnology LLC
"""
    return body


# ---------------------------------------------------------------------------
# SMTP send
# ---------------------------------------------------------------------------

def _send_email(to_email: str, subject: str, body: str) -> bool:
    """Send a plain-text email. Returns True on success."""
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


def send_insights(
    student: dict[str, Any],
    stats: dict[str, Any],
    top_jobs: list[dict[str, Any]],
    new_jobs_count: int = 0,
) -> bool:
    email = student.get("email", "")
    if not email:
        print(f"    No email on record for {student['name']} — skipping.")
        return False

    subject = "Your MCT PathAI Weekly Insights 🎯"
    body = build_email_body(student["name"], stats, top_jobs, new_jobs_count)
    return _send_email(email, subject, body)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run() -> None:
    print("=" * 60)
    print("MCT PathAI — Send Student Insights")
    print("=" * 60)

    client = _get_client()

    new_jobs_count = fetch_new_jobs_since_yesterday(client)
    print(f"New jobs since yesterday: {new_jobs_count}")

    students = fetch_all_students(client)
    if not students:
        print("No students found in database.")
        return

    print(f"\n{len(students)} student(s) to process.\n")

    sent = skipped = failed = 0

    for student in students:
        name = student.get("name", "Student")
        email = student.get("email", "")
        sid   = student["id"]

        print(f"Processing: {name} <{email}>")

        top_jobs     = fetch_top_jobs(client, sid, limit=10)
        total_matches = fetch_total_match_count(client, sid)
        stats        = build_stats(top_jobs, total_matches)

        print(
            f"  matches={total_matches}  top_score={stats['top_score_pct']}%  "
            f"A+={stats['a_plus_count']}  A={stats['a_count']}"
        )

        if not email:
            print(f"  ⏭  No email — skipping.\n")
            skipped += 1
            continue

        ok = send_insights(student, stats, top_jobs, new_jobs_count)
        if ok:
            print(f"  ✅ Insights email sent → {email}\n")
            sent += 1
        else:
            print(f"  ❌ Failed to send → {email}\n")
            failed += 1

    print("=" * 60)
    print(f"Done. {sent} sent, {skipped} skipped (no email), {failed} failed.")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    run()
