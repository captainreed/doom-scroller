import { loadConfig, getProjectRoot } from './config';
import { DatabaseManager } from './database';
import { ReelCollector } from './collector';
import * as fs from 'fs';
import * as path from 'path';

function generateRunId(): string {
  const now = new Date();
  const dateStr = now.toISOString().replace(/[-:T]/g, '').substring(0, 14);
  const random = Math.random().toString(36).substring(2, 8);
  return `run_${dateStr}_${random}`;
}

function log(message: string, logPath: string): void {
  const timestamp = new Date().toISOString();
  const logMessage = `[${timestamp}] ${message}\n`;
  console.log(message);
  fs.appendFileSync(logPath, logMessage);
}

async function main(): Promise<void> {
  const projectRoot = getProjectRoot();
  const config = loadConfig(projectRoot);

  // Setup logging
  const today = new Date().toISOString().split('T')[0];
  const logPath = path.join(config.log_dir, `app_${today}.log`);

  log('Starting Instagram Reels collector...', logPath);
  log(`Daily target: ${config.daily_reel_target} reels`, logPath);

  // Initialize database
  const db = new DatabaseManager(config);
  await db.init();

  // Generate run ID and create run record
  const runId = generateRunId();
  const runDate = today;

  log(`Run ID: ${runId}`, logPath);

  // Check if we should skip (already completed today)
  if (config.skip_if_already_completed_today) {
    const existingCount = db.getReelsCountForDate(runDate);
    if (existingCount >= config.daily_reel_target) {
      log(`Daily quota already met (${existingCount}/${config.daily_reel_target}). Skipping collection.`, logPath);
      db.close();
      return;
    }
  }

  // Create run record
  db.createRun(runId, runDate, config.daily_reel_target);
  db.saveConfigSnapshot(runId, config);

  // Initialize collector
  const collector = new ReelCollector(config, db, runId);

  try {
    // Launch browser
    const launched = await collector.launch();
    if (!launched) {
      log('Failed to launch browser', logPath);
      db.updateRunStatus(runId, 'failed', 'Browser launch failed');
      db.close();
      return;
    }

    // Check login
    const loggedIn = await collector.checkLogin();
    if (!loggedIn) {
      log('Instagram login required. Please log in manually.', logPath);
      db.updateRunStatus(runId, 'failed', 'Login required');
      await collector.close();
      db.close();
      return;
    }

    // Navigate to Reels
    const navigated = await collector.navigateToReels();
    if (!navigated) {
      log('Failed to navigate to Reels feed', logPath);
      db.updateRunStatus(runId, 'failed', 'Failed to navigate to Reels');
      await collector.close();
      db.close();
      return;
    }

    // Collect reels
    const collected = await collector.collectReels(config.daily_reel_target);
    log(`Collection complete: ${collected} reels collected`, logPath);

    // Update run status
    if (collected > 0) {
      db.updateRunStatus(runId, 'completed');
      log('Run completed successfully', logPath);
    } else {
      db.updateRunStatus(runId, 'partial', 'No new reels collected');
      log('Run completed with no new reels', logPath);
    }

  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error);
    log(`Error during collection: ${errorMessage}`, logPath);
    db.updateRunStatus(runId, 'failed', errorMessage);
  } finally {
    await collector.close();
    db.close();
  }

  log('Browser agent finished', logPath);
}

// Run if called directly
main().catch(console.error);
