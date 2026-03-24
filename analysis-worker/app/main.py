import click
from datetime import datetime
from pathlib import Path

from .config import load_config, get_project_root
from .database import DatabaseManager
from .analyzer import ReelAnalyzer
from .report_generator import ReportGenerator


@click.group()
def cli():
    """Instagram Reels Daily Digest - Analysis Worker"""
    pass


@cli.command()
@click.option('--date', default=None, help='Date to process (YYYY-MM-DD). Defaults to today.')
def run_daily(date: str):
    """Run the full daily pipeline: analyze pending reels and generate report."""
    if date is None:
        date = datetime.now().strftime('%Y-%m-%d')

    click.echo(f"Running daily pipeline for {date}...")

    config = load_config()
    db = DatabaseManager(config)

    try:
        # Analyze pending reels
        click.echo("\n=== Analyzing Pending Reels ===")
        analyzer = ReelAnalyzer(config, db)
        analyzed_count = analyzer.analyze_pending_reels()
        click.echo(f"Analyzed {analyzed_count} reels")

        # Generate report
        click.echo("\n=== Generating Report ===")
        generator = ReportGenerator(config, db)
        report_path = generator.generate_report(date)

        if report_path:
            click.echo(f"\nDaily pipeline complete!")
            click.echo(f"Report saved to: {report_path}")
        else:
            click.echo("\nNo report generated (no data for date)")

    finally:
        db.close()


@cli.command()
def analyze_pending():
    """Analyze all reels with pending status."""
    click.echo("Analyzing pending reels...")

    config = load_config()
    db = DatabaseManager(config)

    try:
        analyzer = ReelAnalyzer(config, db)
        count = analyzer.analyze_pending_reels()
        click.echo(f"\nAnalyzed {count} reels")
    finally:
        db.close()


@cli.command()
@click.option('--date', required=True, help='Date to generate report for (YYYY-MM-DD)')
def generate_report(date: str):
    """Generate report for a specific date."""
    click.echo(f"Generating report for {date}...")

    config = load_config()
    db = DatabaseManager(config)

    try:
        generator = ReportGenerator(config, db)
        report_path = generator.generate_report(date)

        if report_path:
            click.echo(f"Report saved to: {report_path}")
        else:
            click.echo("No report generated (no data for date)")
    finally:
        db.close()


@cli.command()
def status():
    """Print today's progress."""
    today = datetime.now().strftime('%Y-%m-%d')

    config = load_config()
    db = DatabaseManager(config)

    try:
        total_reels = db.get_reels_count_for_date(today)
        processed_reels = db.get_processed_reels_count_for_date(today)
        pending_reels = total_reels - processed_reels

        click.echo(f"\n=== Instagram Reels Digest Status ===")
        click.echo(f"Date: {today}")
        click.echo(f"Daily target: {config.daily_reel_target}")
        click.echo(f"Reels collected: {total_reels}")
        click.echo(f"Reels processed: {processed_reels}")
        click.echo(f"Reels pending: {pending_reels}")
        click.echo(f"Progress: {total_reels}/{config.daily_reel_target} ({100*total_reels/config.daily_reel_target:.1f}%)")

    finally:
        db.close()


@cli.command()
def init_db():
    """Initialize the database (creates tables if they don't exist)."""
    click.echo("Initializing database...")

    config = load_config()

    # The DatabaseManager in the TypeScript agent creates the schema
    # But we can also do it from Python by importing the schema
    import sqlite3
    conn = sqlite3.connect(config.database_path)

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS app_config_snapshot (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            daily_reel_target INTEGER NOT NULL,
            report_output_dir TEXT NOT NULL,
            watch_seconds_per_reel INTEGER,
            screenshots_per_reel INTEGER,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS runs (
            id TEXT PRIMARY KEY,
            run_date TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            status TEXT NOT NULL,
            reels_target INTEGER NOT NULL,
            reels_collected INTEGER NOT NULL DEFAULT 0,
            reels_processed INTEGER NOT NULL DEFAULT 0,
            error_message TEXT
        );

        CREATE TABLE IF NOT EXISTS reels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            reel_date TEXT NOT NULL,
            source_url TEXT,
            creator_handle TEXT,
            caption_text TEXT,
            visible_overlay_text TEXT,
            collected_at TEXT NOT NULL,
            watch_duration_sec INTEGER,
            screenshot_count INTEGER NOT NULL DEFAULT 0,
            transcript_text TEXT,
            raw_notes TEXT,
            processing_status TEXT NOT NULL DEFAULT 'pending',
            is_duplicate INTEGER NOT NULL DEFAULT 0,
            UNIQUE(source_url, reel_date),
            FOREIGN KEY (run_id) REFERENCES runs(id)
        );

        CREATE TABLE IF NOT EXISTS reel_screenshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reel_id INTEGER NOT NULL,
            file_path TEXT NOT NULL,
            captured_at TEXT NOT NULL,
            frame_index INTEGER,
            ocr_text TEXT,
            FOREIGN KEY (reel_id) REFERENCES reels(id)
        );

        CREATE TABLE IF NOT EXISTS reel_analysis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reel_id INTEGER NOT NULL UNIQUE,
            short_summary TEXT,
            main_points TEXT,
            topic_tags TEXT,
            category_primary TEXT,
            category_secondary TEXT,
            is_news_related INTEGER NOT NULL DEFAULT 0,
            is_funny INTEGER NOT NULL DEFAULT 0,
            is_educational INTEGER NOT NULL DEFAULT 0,
            is_socially_important INTEGER NOT NULL DEFAULT 0,
            contains_speculation INTEGER NOT NULL DEFAULT 0,
            contains_factual_claims INTEGER NOT NULL DEFAULT 0,
            funny_score REAL,
            educational_score REAL,
            social_importance_score REAL,
            news_relevance_score REAL,
            overall_noteworthiness_score REAL,
            save_flag INTEGER NOT NULL DEFAULT 0,
            analysis_created_at TEXT NOT NULL,
            FOREIGN KEY (reel_id) REFERENCES reels(id)
        );

        CREATE TABLE IF NOT EXISTS claims (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reel_id INTEGER NOT NULL,
            claim_text TEXT NOT NULL,
            claim_type TEXT NOT NULL,
            confidence REAL,
            appears_unsubstantiated INTEGER NOT NULL DEFAULT 0,
            support_status TEXT NOT NULL DEFAULT 'unknown',
            reasoning TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (reel_id) REFERENCES reels(id)
        );

        CREATE TABLE IF NOT EXISTS daily_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_date TEXT NOT NULL UNIQUE,
            run_id TEXT,
            total_reels INTEGER NOT NULL,
            report_markdown_path TEXT NOT NULL,
            report_text_path TEXT,
            generated_at TEXT NOT NULL,
            summary_blob TEXT,
            FOREIGN KEY (run_id) REFERENCES runs(id)
        );

        CREATE INDEX IF NOT EXISTS idx_runs_run_date ON runs(run_date);
        CREATE INDEX IF NOT EXISTS idx_reels_reel_date ON reels(reel_date);
        CREATE INDEX IF NOT EXISTS idx_reels_run_id ON reels(run_id);
        CREATE INDEX IF NOT EXISTS idx_claims_reel_id ON claims(reel_id);
        CREATE INDEX IF NOT EXISTS idx_daily_reports_report_date ON daily_reports(report_date);
    """)

    conn.commit()
    conn.close()

    click.echo(f"Database initialized at: {config.database_path}")


if __name__ == '__main__':
    cli()
