import initSqlJs, { Database as SqlJsDatabase } from 'sql.js';
import * as fs from 'fs';
import * as path from 'path';
import { Config } from './config';

export interface Run {
  id: string;
  run_date: string;
  started_at: string;
  finished_at: string | null;
  status: string;
  reels_target: number;
  reels_collected: number;
  reels_processed: number;
  error_message: string | null;
}

export interface Reel {
  id?: number;
  run_id: string;
  reel_date: string;
  source_url: string | null;
  creator_handle: string | null;
  caption_text: string | null;
  visible_overlay_text: string | null;
  collected_at: string;
  watch_duration_sec: number | null;
  screenshot_count: number;
  transcript_text: string | null;
  raw_notes: string | null;
  processing_status: string;
  is_duplicate: number;
}

export interface ReelScreenshot {
  id?: number;
  reel_id: number;
  file_path: string;
  captured_at: string;
  frame_index: number | null;
  ocr_text: string | null;
}

export class DatabaseManager {
  private db: SqlJsDatabase | null = null;
  private dbPath: string;

  constructor(private config: Config) {
    this.dbPath = config.database_path;
  }

  async init(): Promise<void> {
    const SQL = await initSqlJs();

    // Load existing database if it exists
    if (fs.existsSync(this.dbPath)) {
      const fileBuffer = fs.readFileSync(this.dbPath);
      this.db = new SQL.Database(fileBuffer);
    } else {
      this.db = new SQL.Database();
    }

    this.initSchema();
    this.save();
  }

  private initSchema(): void {
    if (!this.db) throw new Error('Database not initialized');

    this.db.run(`
      CREATE TABLE IF NOT EXISTS app_config_snapshot (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT NOT NULL,
        daily_reel_target INTEGER NOT NULL,
        report_output_dir TEXT NOT NULL,
        watch_seconds_per_reel INTEGER,
        screenshots_per_reel INTEGER,
        created_at TEXT NOT NULL
      )
    `);

    this.db.run(`
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
      )
    `);

    this.db.run(`
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
      )
    `);

    this.db.run(`
      CREATE TABLE IF NOT EXISTS reel_screenshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        reel_id INTEGER NOT NULL,
        file_path TEXT NOT NULL,
        captured_at TEXT NOT NULL,
        frame_index INTEGER,
        ocr_text TEXT,
        FOREIGN KEY (reel_id) REFERENCES reels(id)
      )
    `);

    this.db.run(`
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
      )
    `);

    this.db.run(`
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
      )
    `);

    this.db.run(`
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
      )
    `);

    // Create indexes
    this.db.run(`CREATE INDEX IF NOT EXISTS idx_runs_run_date ON runs(run_date)`);
    this.db.run(`CREATE INDEX IF NOT EXISTS idx_reels_reel_date ON reels(reel_date)`);
    this.db.run(`CREATE INDEX IF NOT EXISTS idx_reels_run_id ON reels(run_id)`);
    this.db.run(`CREATE INDEX IF NOT EXISTS idx_claims_reel_id ON claims(reel_id)`);
    this.db.run(`CREATE INDEX IF NOT EXISTS idx_daily_reports_report_date ON daily_reports(report_date)`);
  }

  private save(): void {
    if (!this.db) return;
    const data = this.db.export();
    const buffer = Buffer.from(data);
    fs.writeFileSync(this.dbPath, buffer);
  }

  createRun(runId: string, runDate: string, reelsTarget: number): void {
    if (!this.db) throw new Error('Database not initialized');

    this.db.run(
      `INSERT INTO runs (id, run_date, started_at, status, reels_target, reels_collected, reels_processed)
       VALUES (?, ?, ?, 'running', ?, 0, 0)`,
      [runId, runDate, new Date().toISOString(), reelsTarget]
    );
    this.save();
  }

  saveConfigSnapshot(runId: string, config: Config): void {
    if (!this.db) throw new Error('Database not initialized');

    this.db.run(
      `INSERT INTO app_config_snapshot (run_id, daily_reel_target, report_output_dir, watch_seconds_per_reel, screenshots_per_reel, created_at)
       VALUES (?, ?, ?, ?, ?, ?)`,
      [
        runId,
        config.daily_reel_target,
        config.report_output_dir,
        config.watch_seconds_per_reel,
        config.screenshots_per_reel,
        new Date().toISOString()
      ]
    );
    this.save();
  }

  getReelsCountForDate(date: string): number {
    if (!this.db) throw new Error('Database not initialized');

    const result = this.db.exec(`SELECT COUNT(*) as count FROM reels WHERE reel_date = ?`, [date]);
    if (result.length > 0 && result[0].values.length > 0) {
      return result[0].values[0][0] as number;
    }
    return 0;
  }

  insertReel(reel: Reel): number {
    if (!this.db) throw new Error('Database not initialized');

    this.db.run(
      `INSERT INTO reels (run_id, reel_date, source_url, creator_handle, caption_text, visible_overlay_text, collected_at, watch_duration_sec, screenshot_count, transcript_text, raw_notes, processing_status, is_duplicate)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [
        reel.run_id,
        reel.reel_date,
        reel.source_url,
        reel.creator_handle,
        reel.caption_text,
        reel.visible_overlay_text,
        reel.collected_at,
        reel.watch_duration_sec,
        reel.screenshot_count,
        reel.transcript_text,
        reel.raw_notes,
        reel.processing_status,
        reel.is_duplicate
      ]
    );

    // Get last insert rowid
    const result = this.db.exec(`SELECT last_insert_rowid()`);
    const lastId = result[0].values[0][0] as number;

    this.save();
    return lastId;
  }

  insertScreenshot(screenshot: ReelScreenshot): void {
    if (!this.db) throw new Error('Database not initialized');

    this.db.run(
      `INSERT INTO reel_screenshots (reel_id, file_path, captured_at, frame_index, ocr_text)
       VALUES (?, ?, ?, ?, ?)`,
      [
        screenshot.reel_id,
        screenshot.file_path,
        screenshot.captured_at,
        screenshot.frame_index,
        screenshot.ocr_text
      ]
    );
    this.save();
  }

  updateRunReelsCollected(runId: string, count: number): void {
    if (!this.db) throw new Error('Database not initialized');

    this.db.run(`UPDATE runs SET reels_collected = ? WHERE id = ?`, [count, runId]);
    this.save();
  }

  updateRunStatus(runId: string, status: string, errorMessage?: string): void {
    if (!this.db) throw new Error('Database not initialized');

    this.db.run(
      `UPDATE runs SET status = ?, finished_at = ?, error_message = ? WHERE id = ?`,
      [status, new Date().toISOString(), errorMessage || null, runId]
    );
    this.save();
  }

  checkReelExists(sourceUrl: string, reelDate: string): boolean {
    if (!this.db) throw new Error('Database not initialized');

    const result = this.db.exec(
      `SELECT COUNT(*) as count FROM reels WHERE source_url = ? AND reel_date = ?`,
      [sourceUrl, reelDate]
    );
    if (result.length > 0 && result[0].values.length > 0) {
      return (result[0].values[0][0] as number) > 0;
    }
    return false;
  }

  close(): void {
    if (this.db) {
      this.save();
      this.db.close();
      this.db = null;
    }
  }
}
