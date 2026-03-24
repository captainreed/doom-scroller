import sqlite3
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime

from .config import Config


@dataclass
class Reel:
    id: int
    run_id: str
    reel_date: str
    source_url: Optional[str]
    creator_handle: Optional[str]
    caption_text: Optional[str]
    visible_overlay_text: Optional[str]
    collected_at: str
    watch_duration_sec: Optional[int]
    screenshot_count: int
    transcript_text: Optional[str]
    raw_notes: Optional[str]
    processing_status: str
    is_duplicate: int


@dataclass
class ReelScreenshot:
    id: int
    reel_id: int
    file_path: str
    captured_at: str
    frame_index: Optional[int]
    ocr_text: Optional[str]


@dataclass
class ReelAnalysis:
    id: Optional[int]
    reel_id: int
    short_summary: Optional[str]
    main_points: Optional[str]
    topic_tags: Optional[str]
    category_primary: Optional[str]
    category_secondary: Optional[str]
    is_news_related: int
    is_funny: int
    is_educational: int
    is_socially_important: int
    contains_speculation: int
    contains_factual_claims: int
    funny_score: Optional[float]
    educational_score: Optional[float]
    social_importance_score: Optional[float]
    news_relevance_score: Optional[float]
    overall_noteworthiness_score: Optional[float]
    save_flag: int
    analysis_created_at: str


@dataclass
class Claim:
    id: Optional[int]
    reel_id: int
    claim_text: str
    claim_type: str
    confidence: Optional[float]
    appears_unsubstantiated: int
    support_status: str
    reasoning: Optional[str]
    created_at: str


class DatabaseManager:
    def __init__(self, config: Config):
        self.db_path = config.database_path
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row

    def get_pending_reels(self) -> List[Reel]:
        """Get all reels with pending processing status."""
        cursor = self.conn.execute(
            "SELECT * FROM reels WHERE processing_status = 'pending'"
        )
        rows = cursor.fetchall()
        return [self._row_to_reel(row) for row in rows]

    def get_reels_for_date(self, date: str) -> List[Reel]:
        """Get all reels for a specific date."""
        cursor = self.conn.execute(
            "SELECT * FROM reels WHERE reel_date = ?", (date,)
        )
        rows = cursor.fetchall()
        return [self._row_to_reel(row) for row in rows]

    def get_screenshots_for_reel(self, reel_id: int) -> List[ReelScreenshot]:
        """Get all screenshots for a reel."""
        cursor = self.conn.execute(
            "SELECT * FROM reel_screenshots WHERE reel_id = ?", (reel_id,)
        )
        rows = cursor.fetchall()
        return [self._row_to_screenshot(row) for row in rows]

    def get_analysis_for_reel(self, reel_id: int) -> Optional[ReelAnalysis]:
        """Get analysis for a reel if it exists."""
        cursor = self.conn.execute(
            "SELECT * FROM reel_analysis WHERE reel_id = ?", (reel_id,)
        )
        row = cursor.fetchone()
        if row:
            return self._row_to_analysis(row)
        return None

    def get_analyses_for_date(self, date: str) -> List[Dict[str, Any]]:
        """Get all analyses with reel info for a specific date."""
        cursor = self.conn.execute("""
            SELECT r.*, ra.*
            FROM reels r
            JOIN reel_analysis ra ON r.id = ra.reel_id
            WHERE r.reel_date = ?
        """, (date,))
        return [dict(row) for row in cursor.fetchall()]

    def get_claims_for_reel(self, reel_id: int) -> List[Claim]:
        """Get all claims for a reel."""
        cursor = self.conn.execute(
            "SELECT * FROM claims WHERE reel_id = ?", (reel_id,)
        )
        rows = cursor.fetchall()
        return [self._row_to_claim(row) for row in rows]

    def get_claims_for_date(self, date: str) -> List[Dict[str, Any]]:
        """Get all claims with reel info for a specific date."""
        cursor = self.conn.execute("""
            SELECT c.*, r.source_url, r.creator_handle, r.caption_text
            FROM claims c
            JOIN reels r ON c.reel_id = r.id
            WHERE r.reel_date = ?
        """, (date,))
        return [dict(row) for row in cursor.fetchall()]

    def save_analysis(self, analysis: ReelAnalysis) -> int:
        """Save or update reel analysis."""
        cursor = self.conn.execute("""
            INSERT OR REPLACE INTO reel_analysis (
                reel_id, short_summary, main_points, topic_tags,
                category_primary, category_secondary, is_news_related,
                is_funny, is_educational, is_socially_important,
                contains_speculation, contains_factual_claims,
                funny_score, educational_score, social_importance_score,
                news_relevance_score, overall_noteworthiness_score,
                save_flag, analysis_created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            analysis.reel_id, analysis.short_summary, analysis.main_points,
            analysis.topic_tags, analysis.category_primary, analysis.category_secondary,
            analysis.is_news_related, analysis.is_funny, analysis.is_educational,
            analysis.is_socially_important, analysis.contains_speculation,
            analysis.contains_factual_claims, analysis.funny_score,
            analysis.educational_score, analysis.social_importance_score,
            analysis.news_relevance_score, analysis.overall_noteworthiness_score,
            analysis.save_flag, analysis.analysis_created_at
        ))
        self.conn.commit()
        return cursor.lastrowid

    def save_claim(self, claim: Claim) -> int:
        """Save a claim."""
        cursor = self.conn.execute("""
            INSERT INTO claims (
                reel_id, claim_text, claim_type, confidence,
                appears_unsubstantiated, support_status, reasoning, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            claim.reel_id, claim.claim_text, claim.claim_type, claim.confidence,
            claim.appears_unsubstantiated, claim.support_status, claim.reasoning,
            claim.created_at
        ))
        self.conn.commit()
        return cursor.lastrowid

    def update_reel_processing_status(self, reel_id: int, status: str) -> None:
        """Update the processing status of a reel."""
        self.conn.execute(
            "UPDATE reels SET processing_status = ? WHERE id = ?",
            (status, reel_id)
        )
        self.conn.commit()

    def update_screenshot_ocr(self, screenshot_id: int, ocr_text: str) -> None:
        """Update OCR text for a screenshot."""
        self.conn.execute(
            "UPDATE reel_screenshots SET ocr_text = ? WHERE id = ?",
            (ocr_text, screenshot_id)
        )
        self.conn.commit()

    def save_daily_report(
        self, report_date: str, run_id: Optional[str],
        total_reels: int, markdown_path: str,
        text_path: Optional[str], summary_blob: Optional[str]
    ) -> int:
        """Save daily report record."""
        cursor = self.conn.execute("""
            INSERT OR REPLACE INTO daily_reports (
                report_date, run_id, total_reels, report_markdown_path,
                report_text_path, generated_at, summary_blob
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            report_date, run_id, total_reels, markdown_path,
            text_path, datetime.now().isoformat(), summary_blob
        ))
        self.conn.commit()
        return cursor.lastrowid

    def get_reels_count_for_date(self, date: str) -> int:
        """Get count of reels for a specific date."""
        cursor = self.conn.execute(
            "SELECT COUNT(*) FROM reels WHERE reel_date = ?", (date,)
        )
        return cursor.fetchone()[0]

    def get_processed_reels_count_for_date(self, date: str) -> int:
        """Get count of processed reels for a specific date."""
        cursor = self.conn.execute(
            "SELECT COUNT(*) FROM reels WHERE reel_date = ? AND processing_status = 'processed'",
            (date,)
        )
        return cursor.fetchone()[0]

    def _row_to_reel(self, row: sqlite3.Row) -> Reel:
        return Reel(
            id=row["id"],
            run_id=row["run_id"],
            reel_date=row["reel_date"],
            source_url=row["source_url"],
            creator_handle=row["creator_handle"],
            caption_text=row["caption_text"],
            visible_overlay_text=row["visible_overlay_text"],
            collected_at=row["collected_at"],
            watch_duration_sec=row["watch_duration_sec"],
            screenshot_count=row["screenshot_count"],
            transcript_text=row["transcript_text"],
            raw_notes=row["raw_notes"],
            processing_status=row["processing_status"],
            is_duplicate=row["is_duplicate"]
        )

    def _row_to_screenshot(self, row: sqlite3.Row) -> ReelScreenshot:
        return ReelScreenshot(
            id=row["id"],
            reel_id=row["reel_id"],
            file_path=row["file_path"],
            captured_at=row["captured_at"],
            frame_index=row["frame_index"],
            ocr_text=row["ocr_text"]
        )

    def _row_to_analysis(self, row: sqlite3.Row) -> ReelAnalysis:
        return ReelAnalysis(
            id=row["id"],
            reel_id=row["reel_id"],
            short_summary=row["short_summary"],
            main_points=row["main_points"],
            topic_tags=row["topic_tags"],
            category_primary=row["category_primary"],
            category_secondary=row["category_secondary"],
            is_news_related=row["is_news_related"],
            is_funny=row["is_funny"],
            is_educational=row["is_educational"],
            is_socially_important=row["is_socially_important"],
            contains_speculation=row["contains_speculation"],
            contains_factual_claims=row["contains_factual_claims"],
            funny_score=row["funny_score"],
            educational_score=row["educational_score"],
            social_importance_score=row["social_importance_score"],
            news_relevance_score=row["news_relevance_score"],
            overall_noteworthiness_score=row["overall_noteworthiness_score"],
            save_flag=row["save_flag"],
            analysis_created_at=row["analysis_created_at"]
        )

    def _row_to_claim(self, row: sqlite3.Row) -> Claim:
        return Claim(
            id=row["id"],
            reel_id=row["reel_id"],
            claim_text=row["claim_text"],
            claim_type=row["claim_type"],
            confidence=row["confidence"],
            appears_unsubstantiated=row["appears_unsubstantiated"],
            support_status=row["support_status"],
            reasoning=row["reasoning"],
            created_at=row["created_at"]
        )

    def close(self) -> None:
        self.conn.close()
