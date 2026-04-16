from __future__ import annotations

import importlib
from pathlib import Path
from typing import Optional

import typer
import yaml
from rich.columns import Columns
from rich.console import Console
from rich.table import Table

from src.core import db
from src.core import supabase_writer
from src.core.models import Resume
from src.core.normalizer import normalize_job
from src.enrichment import category as cat_enricher
from src.enrichment import skills as skills_enricher
from src.enrichment import experience as exp_enricher
from src.enrichment import visa as visa_enricher
from src.scoring.matcher import score_all

app = typer.Typer(name="scraper", help="Job scraper across multiple ATS platforms.")
console = Console()

CONFIG_PATH = Path("config/companies.yaml")
RESUME_PATH = Path("data/resume.txt")


def _load_config() -> dict:
    with CONFIG_PATH.open() as f:
        return yaml.safe_load(f)


def _load_resume() -> Resume:
    if not RESUME_PATH.exists():
        return Resume(raw_text="")
    raw = RESUME_PATH.read_text(encoding="utf-8")
    parsed_skills = skills_enricher.enrich_resume_skills(raw)
    return Resume(raw_text=raw, skills=parsed_skills)


def _get_fetcher(ats: str):
    module = importlib.import_module(f"src.fetchers.{ats}")
    return module.fetch_jobs


@app.command()
def scrape(
    ats: Optional[str] = typer.Option(None, help="Limit to a specific ATS (e.g. greenhouse)"),
    company: Optional[str] = typer.Option(None, help="Limit to a specific company slug"),
    score: bool = typer.Option(True, help="Score jobs against resume"),
    save: bool = typer.Option(False, help="Also save results to Google Sheets (requires credentials)"),
    no_sheets: bool = typer.Option(False, "--no-sheets", help="Skip Google Sheets entirely"),
) -> None:
    """Scrape jobs from configured companies and save to SQLite."""
    db.init_db()

    use_sheets = save and not no_sheets and db.CREDS_PATH.exists()
    if use_sheets:
        db.init_sheets()
    elif save and not no_sheets and not db.CREDS_PATH.exists():
        console.print("[yellow]--save requested but Google Sheets credentials not found; saving to SQLite only.[/yellow]")

    config = _load_config()
    resume = _load_resume() if score else Resume(raw_text="")

    all_jobs = []
    companies = config.get("companies", {})

    for platform, entries in companies.items():
        if ats and platform != ats:
            continue
        try:
            fetcher = _get_fetcher(platform)
        except ModuleNotFoundError:
            console.print(f"[yellow]No fetcher for {platform}, skipping.[/yellow]")
            continue

        for entry in entries:
            if company and entry["slug"] != company:
                continue
            console.print(f"Fetching [bold]{entry['name']}[/bold] ({platform})...")
            try:
                jobs = fetcher(entry)
                enriched = [
                    skills_enricher.enrich_job(normalize_job(j))
                    for j in jobs
                ]
                all_jobs.extend(enriched)
                console.print(f"  [green]{len(enriched)} jobs[/green]")
            except Exception as exc:
                console.print(f"  [red]Error: {exc}[/red]")

    # ── JobSpy sources ────────────────────────────────────────────────────────
    from src.fetchers import jobspy_fetcher
    console.print("\n[bold cyan]Fetching via JobSpy (LinkedIn, Indeed, Glassdoor, ZipRecruiter)...[/bold cyan]")
    try:
        jobspy_jobs, jobspy_source_counts = jobspy_fetcher.fetch_all_jobs()
        for job in jobspy_jobs:
            enriched_j = skills_enricher.enrich_job(normalize_job(job))
            all_jobs.append(enriched_j)
        for site, count in sorted(jobspy_source_counts.items()):
            console.print(f"  [green]{count} jobs[/green] from {site}")
        console.print(f"  [bold]{sum(jobspy_source_counts.values())} total JobSpy jobs[/bold]")
    except Exception as exc:
        console.print(f"  [red]JobSpy error: {exc}[/red]")

    # ── Deduplicate by URL across all sources ─────────────────────────────────
    seen: dict[str, object] = {}
    for job in all_jobs:
        if job.url not in seen:
            seen[job.url] = job
    all_jobs = list(seen.values())  # type: ignore[assignment]

    if score and resume.raw_text:
        all_jobs = score_all(all_jobs, resume)

    # Always save to SQLite
    sqlite_inserted, sqlite_skipped = db.save_jobs_batch(all_jobs)
    console.print(f"\n[bold]{sqlite_inserted} new jobs saved to SQLite[/bold] ({sqlite_skipped} duplicates skipped).")

    if use_sheets:
        sheets_inserted = 0
        for job in all_jobs:
            before = db.job_exists(job.id)
            db.insert_job(job)
            if not before:
                sheets_inserted += 1
        db.log_run(f"scrape: {sheets_inserted} new jobs inserted ({len(all_jobs)} fetched)")
        console.print(f"[bold]{sheets_inserted} new jobs saved to Google Sheets.[/bold]")

    # Write-through to Supabase scraped_jobs table
    sb_upserted, sb_errors = supabase_writer.upsert_jobs(all_jobs)
    if sb_upserted:
        console.print(f"[bold]{sb_upserted} jobs upserted to Supabase.[/bold]")
    if sb_errors:
        console.print(f"[yellow]{sb_errors} jobs failed to upsert to Supabase.[/yellow]")

    _print_table(all_jobs[:25])


@app.command()
def run(
    dry_run: bool = typer.Option(True, "--dry-run/--no-dry-run", help="Skip all Sheets writes"),
    debug: bool = typer.Option(False, "--debug/--no-debug", help="Print per-job detail and errors"),
) -> None:
    """Fetch → normalize → geo gate → exp filter. Live mode writes to Sheets."""
    db.init_db()
    if not dry_run:
        db.init_sheets()

    config = _load_config()
    companies = config.get("companies", {})

    summary_rows: list[tuple] = []
    total_fetched = total_geo = total_exp = 0
    zero_fetchers: list[tuple[str, str, str]] = []
    qualifying_jobs = []

    for platform, entries in companies.items():
        try:
            fetcher = _get_fetcher(platform)
        except ModuleNotFoundError:
            for entry in entries:
                zero_fetchers.append((entry["name"], platform, "No fetcher module"))
            continue

        for entry in entries:
            company_name = entry["name"]
            console.print(f"Fetching [bold]{company_name}[/bold] ({platform})...", end=" ")
            try:
                raw_jobs = fetcher(entry)
            except Exception as exc:
                reason = f"{type(exc).__name__}: {exc}"
                console.print("[red]ERROR[/red]")
                if debug:
                    console.print(f"  [dim]{reason}[/dim]")
                zero_fetchers.append((company_name, platform, reason))
                summary_rows.append((company_name, platform, 0, 0, 0, 0))
                continue

            fetched = len(raw_jobs)
            console.print(f"[green]{fetched} jobs[/green]")

            geo_pass = exp_pass = would_insert = 0
            for raw in raw_jobs:
                try:
                    job = normalize_job(raw)
                except Exception as exc:
                    if debug:
                        console.print(f"  [yellow]normalize error: {exc}[/yellow]")
                    continue

                if job.is_usa_job:
                    geo_pass += 1
                    exp_ok = job.years_min is None or job.years_min <= 5
                    if exp_ok:
                        exp_pass += 1
                        would_insert += 1
                        qualifying_jobs.append(job)

            total_fetched += fetched
            total_geo += geo_pass
            total_exp += exp_pass
            summary_rows.append((company_name, platform, fetched, geo_pass, exp_pass, would_insert))

            if fetched == 0:
                zero_fetchers.append((company_name, platform, "Fetcher returned 0 jobs"))

    # ── Summary table ──────────────────────────────────────────────────────
    console.print()
    table = Table(show_header=True, header_style="bold cyan", title="Pipeline Summary")
    table.add_column("Company", width=14)
    table.add_column("ATS", width=12)
    table.add_column("Fetched", justify="right", width=8)
    table.add_column("Passed Geo", justify="right", width=10)
    table.add_column("Passed Exp", justify="right", width=10)
    table.add_column("Would Insert", justify="right", width=12)

    for company_name, platform, fetched, geo, exp, insert in summary_rows:
        table.add_row(
            company_name, platform,
            str(fetched),
            f"[green]{geo}[/green]" if geo else "[dim]0[/dim]",
            f"[green]{exp}[/green]" if exp else "[dim]0[/dim]",
            f"[bold green]{insert}[/bold green]" if insert else "[dim]0[/dim]",
        )

    console.print(table)

    console.print(f"\n[bold]Totals[/bold]")
    console.print(f"  Total fetched:            [cyan]{total_fetched}[/cyan]")
    console.print(f"  Passed geography gate:    [cyan]{total_geo}[/cyan]  (is_usa_job=True)")
    console.print(f"  Passed experience filter: [cyan]{total_exp}[/cyan]  (years_min <= 5 or unknown)")

    if zero_fetchers:
        console.print(f"\n[bold yellow]Fetchers that returned 0 jobs:[/bold yellow]")
        for company_name, platform, reason in zero_fetchers:
            console.print(f"  [yellow]{company_name}[/yellow] ({platform}): {reason}")

    if dry_run:
        console.print("\n[dim]Dry run — nothing written to Google Sheets.[/dim]")
    else:
        # Live mode: batch insert qualifying jobs (single API read + single write)
        console.print(f"\nInserting [bold]{len(qualifying_jobs)}[/bold] qualifying jobs to Sheets...")
        inserted, skipped = db.batch_insert_jobs(qualifying_jobs)
        db.log_run(
            f"run: {inserted} new jobs inserted, {skipped} duplicates skipped "
            f"({total_fetched} fetched)"
        )
        console.print(
            f"  [green]{inserted}[/green] new  |  [dim]{skipped}[/dim] already existed"
        )
        # Show total row count in Sheets
        total_in_sheets = len(db.get_jobs())
        console.print(f"\n[bold]Google Sheets: {total_in_sheets} total rows in Jobs tab.[/bold]")

        # Write-through to Supabase scraped_jobs table
        sb_upserted, sb_errors = supabase_writer.upsert_jobs(qualifying_jobs)
        if sb_upserted:
            console.print(f"[bold]{sb_upserted} jobs upserted to Supabase.[/bold]")
        if sb_errors:
            console.print(f"[yellow]{sb_errors} jobs failed to upsert to Supabase.[/yellow]")


@app.command()
def enrich() -> None:
    """Enrich all jobs in SQLite with experience, visa, and category data."""
    db.init_db()
    db.init_sheets()
    console.print("Loading jobs...")
    jobs = db.get_jobs()
    console.print(f"  Loaded [cyan]{len(jobs)}[/cyan] jobs")

    if not jobs:
        console.print("[yellow]No jobs found.[/yellow]")
        raise typer.Exit()

    enriched = []
    for job in jobs:
        j = skills_enricher.enrich_job(job)
        j = exp_enricher.enrich_job(j)
        j = visa_enricher.enrich_job(j)
        j = cat_enricher.enrich_job(j)
        enriched.append(j)

    console.print(f"Saving {len(enriched)} enriched jobs back to Sheets...")
    db.replace_all_jobs(enriched)
    db.log_run(f"enrich: {len(enriched)} jobs enriched")

    # Quick summary stats
    from collections import Counter
    cat_counts = Counter(j.job_category.value for j in enriched)
    exp_counts = Counter(j.experience_level.value for j in enriched)
    h1b_yes = sum(1 for j in enriched if j.h1b_sponsor is True)
    entry_elig = sum(1 for j in enriched if j.is_entry_eligible)

    console.print("\n[bold]Enrichment summary:[/bold]")
    console.print(f"  Entry eligible:  [cyan]{entry_elig}[/cyan]")
    console.print(f"  H1B sponsor:     [cyan]{h1b_yes}[/cyan]")

    exp_table = Table(title="By Experience Level", show_header=True, header_style="bold")
    exp_table.add_column("Level", width=15)
    exp_table.add_column("Count", justify="right", width=8)
    for level, count in exp_counts.most_common():
        exp_table.add_row(level, str(count))
    console.print(exp_table)

    cat_table = Table(title="By Category", show_header=True, header_style="bold")
    cat_table.add_column("Category", width=25)
    cat_table.add_column("Count", justify="right", width=8)
    for cat, count in cat_counts.most_common():
        cat_table.add_row(cat, str(count))
    console.print(cat_table)

    console.print("\n[bold green]Enrichment complete.[/bold green]")


@app.command()
def score(
    resume_path: Path = typer.Option(Path("data/resume.txt"), help="Path to resume file"),
) -> None:
    """Score all jobs against the resume, update fit_score."""
    db.init_db()
    resume = _load_resume()
    if not resume.raw_text:
        console.print(f"[red]Resume not found at {RESUME_PATH}[/red]")
        raise typer.Exit(1)

    console.print(
        f"Resume skills detected: [cyan]{', '.join(resume.skills) or 'none'}[/cyan]"
    )

    console.print("\nLoading jobs from SQLite...")
    jobs = db.get_jobs()
    console.print(f"  Scoring [cyan]{len(jobs)}[/cyan] jobs...")

    scored = score_all(jobs, resume)

    console.print("Saving fit_score values to SQLite...")
    updated = db.update_fit_scores(scored)
    console.print(f"  [green]{updated}[/green] rows updated")
    db.log_run(f"score: {len(scored)} jobs scored")

    # Score distribution bands
    bands: dict[str, int] = {"0.7+": 0, "0.5-0.7": 0, "0.3-0.5": 0, "0.1-0.3": 0, "<0.1": 0}
    for j in scored:
        s = j.fit_score or 0.0
        if s >= 0.7:
            bands["0.7+"] += 1
        elif s >= 0.5:
            bands["0.5-0.7"] += 1
        elif s >= 0.3:
            bands["0.3-0.5"] += 1
        elif s >= 0.1:
            bands["0.1-0.3"] += 1
        else:
            bands["<0.1"] += 1

    dist = Table(title="Score Distribution", show_header=True, header_style="bold cyan")
    dist.add_column("Band", width=12)
    dist.add_column("Count", justify="right", width=8)
    for band, count in bands.items():
        dist.add_row(band, f"[green]{count}[/green]" if count else "[dim]0[/dim]")
    console.print(dist)

    top5 = scored[:5]
    if top5:
        console.print("\n[bold]Top 5 matches:[/bold]")
        _print_table(top5)

    console.print(f"\n[bold green]Scored {len(scored)} jobs.[/bold green]")


@app.command()
def show(
    min_score: float = typer.Option(0.0, help="Minimum fit_score"),
    entry_only: bool = typer.Option(False, "--entry-only/--no-entry-only", help="Entry-eligible only"),
    h1b_only: bool = typer.Option(False, "--h1b-only/--no-h1b-only", help="H1B sponsor only"),
    stem_opt: bool = typer.Option(False, "--stem-opt/--no-stem-opt", help="STEM OPT eligible only"),
    remote_only: bool = typer.Option(False, "--remote-only/--no-remote-only", help="Remote only"),
    opt_friendly: bool = typer.Option(False, "--opt-friendly/--no-opt-friendly", help="OPT-friendly only"),
    region: Optional[str] = typer.Option(None, help="Filter by US region"),
    category: Optional[str] = typer.Option(None, help="Filter by job category"),
    limit: int = typer.Option(25, help="Max rows to display"),
) -> None:
    """Show filtered jobs from SQLite."""
    db.init_db()
    filters: dict = {}
    if min_score > 0.0:
        filters["min_score"] = min_score
    if entry_only:
        filters["is_entry_eligible"] = True
    if h1b_only:
        filters["h1b_sponsor"] = True
    if stem_opt:
        filters["stem_opt_eligible"] = True
    if remote_only:
        filters["work_mode"] = "remote"
    if opt_friendly:
        filters["opt_friendly"] = True
    if region:
        filters["usa_region"] = region
    if category:
        filters["job_category"] = category

    jobs = db.get_jobs(filters)
    active_filters = [k for k in filters]
    if active_filters:
        console.print(f"[dim]Filters: {', '.join(active_filters)}[/dim]")
    _print_table(jobs[:limit])


@app.command()
def stats() -> None:
    """Show a 4-panel aggregate statistics dashboard."""
    db.init_db()
    db.init_sheets()
    console.print("Computing statistics...")
    s = db.get_stats()

    overview = Table(title="Overview", show_header=False, box=None)
    overview.add_column("Metric", width=22, style="cyan")
    overview.add_column("Value", justify="right", width=8)
    overview.add_row("Total jobs", str(s["total_jobs"]))
    overview.add_row("Remote", str(s["remote_count"]))
    overview.add_row("Hybrid", str(s["hybrid_count"]))
    overview.add_row("On-site", str(s["onsite_count"]))

    experience = Table(title="Experience", show_header=False, box=None)
    experience.add_column("Metric", width=22, style="cyan")
    experience.add_column("Value", justify="right", width=8)
    experience.add_row("Entry eligible", str(s["entry_eligible_count"]))
    experience.add_row("New grad", str(s["new_grad_count"]))
    experience.add_row("Junior", str(s["junior_count"]))

    visa = Table(title="Visa", show_header=False, box=None)
    visa.add_column("Metric", width=22, style="cyan")
    visa.add_column("Value", justify="right", width=8)
    visa.add_row("H1B sponsor", str(s["h1b_sponsor_count"]))
    visa.add_row("OPT friendly", str(s["opt_friendly_count"]))
    visa.add_row("STEM OPT eligible", str(s["stem_opt_count"]))

    categories = Table(title="By Category", show_header=True, header_style="bold")
    categories.add_column("Category", width=22)
    categories.add_column("Count", justify="right", width=8)
    for cat, count in s["by_job_category"].items():
        categories.add_row(cat, str(count))

    console.print(Columns([overview, experience, visa, categories]))

    regions = Table(title="By Region", show_header=True, header_style="bold")
    regions.add_column("Region", width=20)
    regions.add_column("Count", justify="right", width=8)
    for region, count in s["by_usa_region"].items():
        regions.add_row(region, str(count))
    console.print(regions)

    console.print(f"\n[dim]Last updated: {s['last_updated']}[/dim]")


@app.command()
def pipeline() -> None:
    """Full pipeline: fetch → insert → enrich → score. Used by Task Scheduler."""
    console.print("[bold cyan]--- STEP 1: Fetch and insert ---[/bold cyan]")
    db.init_db()
    db.init_sheets()
    config = _load_config()
    companies = config.get("companies", {})

    qualifying_jobs = []
    for platform, entries in companies.items():
        try:
            fetcher = _get_fetcher(platform)
        except ModuleNotFoundError:
            continue
        for entry in entries:
            try:
                raw_jobs = fetcher(entry)
            except Exception as exc:
                console.print(f"  [red]{entry['name']}: {exc}[/red]")
                continue
            for raw in raw_jobs:
                try:
                    job = normalize_job(raw)
                except Exception:
                    continue
                if job.is_usa_job and (job.years_min is None or job.years_min <= 5):
                    qualifying_jobs.append(job)

    ats_qualifying_count = len(qualifying_jobs)

    # ── JobSpy sources ────────────────────────────────────────────────────────
    from src.fetchers import jobspy_fetcher
    console.print("  Fetching via JobSpy (LinkedIn, Indeed, Glassdoor, ZipRecruiter)...")
    jobspy_source_counts: dict[str, int] = {}
    try:
        jobspy_jobs, jobspy_source_counts = jobspy_fetcher.fetch_all_jobs()
        for job in jobspy_jobs:
            try:
                normalized = normalize_job(job)
            except Exception:
                continue
            if normalized.is_usa_job and (normalized.years_min is None or normalized.years_min <= 5):
                qualifying_jobs.append(normalized)
        for site, count in sorted(jobspy_source_counts.items()):
            console.print(f"    [green]{count} jobs[/green] from {site}")
    except Exception as exc:
        console.print(f"  [red]JobSpy error: {exc}[/red]")

    # Deduplicate qualifying jobs by URL
    seen_urls: dict[str, object] = {}
    for job in qualifying_jobs:
        if job.url not in seen_urls:
            seen_urls[job.url] = job
    qualifying_jobs = list(seen_urls.values())  # type: ignore[assignment]

    console.print(f"  ATS jobs: [cyan]{ats_qualifying_count}[/cyan]  |  JobSpy jobs: [cyan]{sum(jobspy_source_counts.values())}[/cyan]  |  Total (deduped): [cyan]{len(qualifying_jobs)}[/cyan]")

    total_inserted = db.insert_jobs_batch(qualifying_jobs)
    console.print(f"  [green]{total_inserted}[/green] new jobs inserted")

    console.print("\n[bold cyan]--- STEP 2: Enrich ---[/bold cyan]")
    # Use in-memory jobs — no read from Sheets during pipeline
    enriched = [
        cat_enricher.enrich_job(visa_enricher.enrich_job(
            exp_enricher.enrich_job(skills_enricher.enrich_job(j))
        ))
        for j in qualifying_jobs
    ]
    db.replace_all_jobs(enriched)
    console.print(f"  [green]{len(enriched)}[/green] jobs enriched")

    console.print("\n[bold cyan]--- STEP 3: Score ---[/bold cyan]")
    resume = _load_resume()
    final_jobs = enriched
    if resume.raw_text:
        scored = score_all(enriched, resume)
        db.replace_all_jobs(scored)
        console.print(f"  [green]{len(scored)}[/green] jobs scored")
        final_jobs = scored
    else:
        console.print("  [yellow]No resume found — skipping scoring.[/yellow]")

    # Write-through to Supabase scraped_jobs table (scored jobs if available, else enriched)
    console.print(f"\n[bold cyan]--- STEP 4: Sync to Supabase ---[/bold cyan]")
    sb_upserted, sb_errors = supabase_writer.upsert_jobs(final_jobs)
    if sb_upserted:
        console.print(f"  [green]{sb_upserted}[/green] jobs upserted to Supabase scraped_jobs")
    if sb_errors:
        console.print(f"  [yellow]{sb_errors}[/yellow] jobs failed to upsert")

    db.log_run(f"pipeline: {total_inserted} new jobs, {len(enriched)} enriched, {sb_upserted} synced to Supabase")
    console.print("\n[bold green]Pipeline complete.[/bold green]")


@app.command()
def clean(
    dry_run: bool = typer.Option(True, "--dry-run/--no-dry-run", help="Skip Sheets writes"),
) -> None:
    """Remove expired jobs (older than 30 days)."""
    db.init_db()
    db.init_sheets()
    from datetime import datetime, timezone
    jobs = db.get_jobs()
    now = datetime.now(tz=timezone.utc)
    active = [j for j in jobs if j.expires_at is None or j.expires_at.replace(tzinfo=timezone.utc) > now]
    removed = len(jobs) - len(active)
    console.print(f"Total jobs: [cyan]{len(jobs)}[/cyan]  |  Expired: [yellow]{removed}[/yellow]  |  Keeping: [green]{len(active)}[/green]")
    if removed == 0:
        console.print("[dim]Nothing to clean.[/dim]")
        return
    if dry_run:
        console.print("[dim]Dry run — nothing written to Sheets.[/dim]")
    else:
        db.replace_all_jobs(active)
        db.log_run(f"clean: removed {removed} expired jobs")
        console.print(f"[bold green]Removed {removed} expired jobs.[/bold green]")


@app.command()
def list_jobs(
    min_score: float = typer.Option(0.0, help="Minimum match score"),
    remote_only: bool = typer.Option(False, help="Show only remote jobs"),
    limit: int = typer.Option(25, help="Max rows to display"),
) -> None:
    """List jobs from SQLite."""
    db.init_db()
    filters: dict = {}
    if min_score:
        filters["min_score"] = min_score
    if remote_only:
        filters["work_mode"] = "remote"
    jobs = db.get_jobs(filters)
    _print_table(jobs[:limit])


def _print_table(jobs) -> None:
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Score", width=6)
    table.add_column("Company", width=12)
    table.add_column("Title", width=40)
    table.add_column("Location", width=20)
    table.add_column("ATS", width=10)

    for job in jobs:
        score_str = f"{job.fit_score:.2f}" if job.fit_score is not None else "-"
        location = job.location or ("Remote" if job.work_mode.value == "remote" else "-")
        table.add_row(score_str, job.company, job.title, location, job.ats_platform)

    console.print(table)
    console.print(f"[dim]{len(jobs)} jobs shown[/dim]")


if __name__ == "__main__":
    app()
