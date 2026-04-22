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
# University extraction — two-pass approach
# ---------------------------------------------------------------------------

# Pass 1 (strict, IGNORECASE): handles common formats like "Texas A&M University",
# "University of Washington", "at/from X University".  Works for ~70% of resumes.
# Uses [ \t]+ instead of \s+ between words so the match cannot hop across newlines
# and accidentally join tech-stack words with a University keyword further down.
_INSTITUTION_RE = re.compile(
    r"(?:"
    r"(?:[\w&.,'\-]+(?:[ \t]+[\w&.,'\-]+){0,5}[ \t]+University(?:[ \t]+of[ \t]+[ \t\w,]{1,25})?)"
    r"|(?:University[ \t]+of[ \t]+[ \t\w,]{1,30})"
    r"|(?:[\w&.,'\-]+(?:[ \t]+[\w&.,'\-]+){0,5}[ \t]+Institute[ \t]+of[ \t]+Technology)"
    r"|(?:[\w&.,'\-]+(?:[ \t]+[\w&.,'\-]+){0,5}[ \t]+College(?:[ \t]+of[ \t]+[ \t\w,]{1,20})?)"
    r")",
    re.IGNORECASE,
)

# Pass 2 (loose, proper-noun only): anchored to whitespace/separators so the degree
# field words before the comma/dash are never included in the match.  Handles patterns
# like "B.S. in Data Analytics, Oklahoma City University" and
# "Computer Science - University of North Texas".
# No IGNORECASE — requires capitalized proper nouns to avoid false positives.
_INSTITUTION_LOOSE_RE = re.compile(
    r"(?:\s|[,\-—])\s*"      # anchor: whitespace, comma, hyphen, or em-dash
    r"("
    # "University of X" (e.g. "University of North Texas")
    r"University\s+of\s+[A-Z][A-Za-z][A-Za-z\s]{1,30}"
    # "X University [of Y]" (e.g. "Oklahoma City University", "Texas Tech University")
    r"|[A-Z][A-Za-z&.']*(?:\s+[A-Z][A-Za-z&.']*){0,6}"
    r"\s+University(?:\s+of\s+[A-Z][A-Za-z][A-Za-z\s]{1,25})?"
    # "X College [of Y]" (e.g. "Concordia College", "College of Charleston")
    r"|[A-Z][A-Za-z&.']*(?:\s+[A-Z][A-Za-z&.']*){0,6}"
    r"\s+College(?:\s+of\s+[A-Z][A-Za-z][A-Za-z\s]{1,20})?"
    # "X Institute of Technology"
    r"|[A-Z][A-Za-z&.']*(?:\s+[A-Z][A-Za-z&.']*){0,6}\s+Institute\s+of\s+Technology"
    r")",
    re.MULTILINE,
)

# Words that cannot be the FIRST word of an institution name.
# Includes prepositions, filler words, section headers, and months so patterns
# like "attended X Univ", "Education University of Y", "Dec 2025 University of Z"
# are rejected at the first-word check.  Note: "the" is handled separately
# (strips it and retries) rather than flat-rejecting.
_FIRST_WORD_REJECTS = frozenset({
    "bachelor", "master", "science", "arts", "engineering", "technology",
    "business", "administration", "information", "computer", "data",
    "applied", "analytics", "management", "finance", "accounting",
    "education", "skills", "summary", "experience", "certifications",
    "of", "in", "and", "at", "from", "attended", "graduated",
    "jan", "feb", "mar", "apr", "may", "jun",
    "jul", "aug", "sep", "oct", "nov", "dec",
    "january", "february", "march", "april", "june", "july",
    "august", "september", "october", "november", "december",
})

# Words that, when found in the text BEFORE the last comma, indicate the match
# starts in a degree-field phrase rather than an institution name.
# Excludes prepositions like "of"/"at" because they appear in valid names
# e.g. "University of North Texas, Denton,TX".
_PREFIX_DEGREE_WORDS = frozenset({
    "bachelor", "master", "science", "arts", "engineering",
    "business", "administration", "information", "computer", "data",
    "applied", "analytics", "management", "finance", "accounting",
})


def _validate_institution(raw: str, *, _depth: int = 0) -> str | None:
    """Return cleaned institution string if it passes sanity checks."""
    # Collapse to first line — cross-line matches are never a single institution name
    raw = raw.split("\n")[0].split("\r")[0]
    raw = raw.strip().rstrip(".,;:()")
    words = raw.split()
    if len(words) < 2 or len(words) > 8 or len(raw) > 80:
        return None
    # First word must be a proper noun (capitalized) — rejects "attended X Univ"
    if not words[0][0].isupper():
        return None
    # Strip leading "The" and retry — e.g. "The University of Memphis" → "University of Memphis"
    if words[0].lower() == "the" and _depth == 0 and len(words) >= 3:
        return _validate_institution(" ".join(words[1:]), _depth=1)
    # Reject if first word is a known filler/preposition/degree word/month
    if words[0].lower() in _FIRST_WORD_REJECTS:
        return None
    # Reject matches with purely numeric tokens (years, codes) — catches "Dec 2025 University"
    if any(w.isdigit() for w in words):
        return None
    # If there is a comma, check that the text before the last comma does not
    # contain degree-field content words — catches "B.S. in Computer Science, Texas Tech Univ"
    # but allows "University of North Texas, Denton,TX" (prepositions are fine).
    if "," in raw:
        prefix = raw[: raw.rindex(",")]
        if any(w.lower() in _PREFIX_DEGREE_WORDS for w in prefix.split()):
            return None
    return raw


def extract_university(text: str) -> str | None:
    """
    Extract institution name from resume text using a two-pass approach.

    Pass 1 — strict regex (IGNORECASE, no-newline-crossing).  Tries every match
              in order until one passes validation.
    Pass 2 — whitespace/separator-anchored regex requiring proper-noun capitalization;
              catches "B.S. in X, Oklahoma City University" patterns.  Also tries
              every match in order so that a bad first match (e.g. "Education Univ")
              does not block a valid second match.

    Returns the first clean match, or None if nothing plausible is found.
    """
    # Pass 1 — iterate matches so a rejected first hit doesn't block a valid one
    pos = 0
    while True:
        match = _INSTITUTION_RE.search(text, pos)
        if not match:
            break
        result = _validate_institution(match.group(0))
        if result:
            return result
        pos = match.start() + 1

    # Pass 2 — same sliding-window approach for separator-anchored patterns
    pos = 0
    while True:
        match = _INSTITUTION_LOOSE_RE.search(text, pos)
        if not match:
            break
        result = _validate_institution(match.group(1))
        if result:
            return result
        pos = match.start() + 1

    return None


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
    role_tracks: list[str] | None = None,
    university: str | None = None,
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
    if role_tracks:
        payload["role_tracks"] = role_tracks
    elif role_track and role_track != "general":
        payload["role_tracks"] = [role_track]
    if university:
        payload["university"] = university
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
            university = extract_university(text)
            record = upsert_student(
                client,
                name=name,
                filename=path.name,
                resume_text=text,
                skills=skills,
                university=university,
            )
            student_id = record.get("id", "unknown")
            print(f"OK  id={student_id[:8]}  skills={len(skills)}  university={university or '—'}")
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
