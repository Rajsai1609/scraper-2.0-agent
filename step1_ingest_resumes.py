#!/usr/bin/env python3
"""
Step 1 -- Ingest student resumes into Supabase (MCT-Alesia).

Reads every .pdf and .docx file from the RESUME_DIR, extracts text and
skills, then upserts each student record into the `students` table.
Idempotent -- re-running updates skills/resume_text but keeps the same UUID.

Run once locally after adding / updating resumes:
    python step1_ingest_resumes.py

Extra deps (install locally -- not needed in CI):
    pip install pypdf python-docx supabase python-dotenv

Required env vars (add to .env or export before running):
    SUPABASE_URL          https://xxxx.supabase.co
    SUPABASE_SERVICE_KEY  service_role key (write access)
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

RESUME_DIR = Path(os.getenv("RESUME_DIR", r"D:\STUDENT RESUMES"))
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

SUPPORTED_EXTENSIONS = {".pdf", ".docx"}


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def _extract_pdf(path: Path) -> str:
    """Extract all text from a PDF file using pypdf."""
    try:
        from pypdf import PdfReader  # type: ignore[import]
    except ImportError:
        raise ImportError("pypdf not installed -- run: pip install pypdf")

    reader = PdfReader(str(path))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages).strip()


def _extract_docx(path: Path) -> str:
    """Extract all paragraph text from a DOCX file using python-docx."""
    try:
        from docx import Document  # type: ignore[import]
    except ImportError:
        raise ImportError("python-docx not installed -- run: pip install python-docx")

    doc = Document(str(path))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n".join(paragraphs).strip()


def extract_text(path: Path) -> str:
    """Dispatch to the appropriate extractor based on file extension."""
    ext = path.suffix.lower()
    if ext == ".pdf":
        return _extract_pdf(path)
    if ext == ".docx":
        return _extract_docx(path)
    raise ValueError(f"Unsupported file type: {ext}")


# ---------------------------------------------------------------------------
# Name extraction
# ---------------------------------------------------------------------------

def extract_name(filename: str) -> str:
    """
    Derive a human-readable name from a resume filename.

    Examples:
      "Akhila Resume.docx"       -> "Akhila"
      "MPavan Resume.docx"       -> "M Pavan"
      "Sucharan-Resume.pdf"      -> "Sucharan"
      "Unnatha_BI_Resume.docx"   -> "Unnatha Bi"
      "vinit Resume.pdf"         -> "Vinit"
    """
    stem = Path(filename).stem  # strip extension
    # Remove "Resume" and everything that follows (plus preceding separators)
    stem = re.sub(r"[\s\-_]*resume.*$", "", stem, flags=re.IGNORECASE)
    # Split camelCase: "MPavan" -> "M Pavan"
    stem = re.sub(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", stem)
    # Replace underscores / hyphens with spaces, normalize whitespace
    stem = re.sub(r"[\-_]+", " ", stem)
    # Title-case each token
    return " ".join(w.capitalize() for w in stem.split() if w)


# ---------------------------------------------------------------------------
# Skill extraction (reuse existing pipeline enricher)
# ---------------------------------------------------------------------------

def extract_skills(text: str) -> list[str]:
    """Extract skills from resume text using the existing skills enricher."""
    try:
        from src.enrichment.skills import enrich_resume_skills  # type: ignore[import]
        return enrich_resume_skills(text)
    except Exception:
        # Fallback: return empty list so ingestion doesn't fail
        return []


# ---------------------------------------------------------------------------
# Supabase upsert
# ---------------------------------------------------------------------------

def _get_supabase_client():
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise EnvironmentError(
            "Missing SUPABASE_URL or SUPABASE_SERVICE_KEY environment variables.\n"
            "Add them to .env or export them before running."
        )
    try:
        from supabase import create_client  # type: ignore[import]
    except ImportError:
        raise ImportError("supabase not installed -- run: pip install supabase")
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def upsert_student(
    client,
    *,
    name: str,
    filename: str,
    resume_text: str,
    skills: list[str],
    role_track: str | None = None,
) -> dict:
    """Upsert a student record; dedup key is `filename`."""
    payload: dict = {
        "name": name,
        "filename": filename,
        "resume_text": resume_text,
        "skills": skills,
    }
    if role_track:
        payload["role_track"] = role_track
    result = (
        client.table("students")
        .upsert(payload, on_conflict="filename")
        .execute()
    )
    return result.data[0] if result.data else {}


# ---------------------------------------------------------------------------
# Main ingestion loop
# ---------------------------------------------------------------------------

def run() -> None:
    if not RESUME_DIR.exists():
        print(f"ERROR: Resume directory not found: {RESUME_DIR}", file=sys.stderr)
        sys.exit(1)

    resume_files = [
        p for p in RESUME_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
    ]

    if not resume_files:
        print(f"No .pdf or .docx files found in {RESUME_DIR}")
        return

    print(f"Found {len(resume_files)} resume(s) in {RESUME_DIR}\n")

    client = _get_supabase_client()

    inserted = 0
    errors: list[str] = []

    for path in sorted(resume_files):
        name = extract_name(path.name)
        print(f"  {path.name}  ->  {name!r} ...", end=" ", flush=True)

        try:
            text = extract_text(path)
            if not text.strip():
                print("⚠  empty text -- skipped")
                errors.append(f"{path.name}: empty text")
                continue

            skills = extract_skills(text)
            record = upsert_student(
                client,
                name=name,
                filename=path.name,
                resume_text=text,
                skills=skills,
            )
            student_id = record.get("id", "unknown")
            print(f"OK  id={student_id[:8]}  skills={len(skills)}")
            inserted += 1

        except Exception as exc:
            print(f"ERR  {exc}")
            errors.append(f"{path.name}: {exc}")

    print(f"\n{'='*50}")
    print(f"Ingested:  {inserted}/{len(resume_files)}")
    if errors:
        print(f"Errors ({len(errors)}):")
        for e in errors:
            print(f"  - {e}")
    else:
        print("All resumes ingested successfully.")


if __name__ == "__main__":
    run()
