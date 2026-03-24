import { chromium, Browser, BrowserContext, Page } from 'playwright';
import * as fs from 'fs';
import * as path from 'path';
import { Config } from './config';
import { DatabaseManager, Reel, ReelScreenshot } from './database';

export class ReelCollector {
  private config: Config;
  private db: DatabaseManager;
  private browser: Browser | null = null;
  private context: BrowserContext | null = null;
  private page: Page | null = null;
  private runId: string;
  private runDate: string;
  private reelsCollected: number = 0;

  constructor(config: Config, db: DatabaseManager, runId: string) {
    this.config = config;
    this.db = db;
    this.runId = runId;
    this.runDate = new Date().toISOString().split('T')[0];
  }

  async launch(): Promise<boolean> {
    try {
      console.log('Launching browser...');

      this.browser = await chromium.launchPersistentContext(
        this.config.browser_profile_dir,
        {
          headless: this.config.headless,
          viewport: { width: 430, height: 932 }, // Mobile-ish viewport for reels
          userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
        }
      );

      this.context = this.browser;
      this.page = this.context.pages()[0] || await this.context.newPage();

      console.log('Browser launched successfully');
      return true;
    } catch (error) {
      console.error('Failed to launch browser:', error);
      return false;
    }
  }

  async checkLogin(): Promise<boolean> {
    if (!this.page) return false;

    try {
      console.log('Navigating to Instagram...');
      await this.page.goto('https://www.instagram.com/', { waitUntil: 'networkidle', timeout: 30000 });

      // Wait a bit for any redirects
      await this.page.waitForTimeout(3000);

      const currentUrl = this.page.url();

      // Check if we're on login page
      if (currentUrl.includes('/accounts/login')) {
        console.log('Not logged in. Please log in manually in the browser window.');
        console.log('After logging in, the script will continue automatically.');

        // Wait for navigation away from login page (user logs in manually)
        try {
          await this.page.waitForURL(url => !url.toString().includes('/accounts/login'), { timeout: 300000 }); // 5 min timeout
          console.log('Login detected!');
          await this.page.waitForTimeout(3000);
          return true;
        } catch {
          console.log('Login timeout - please try again');
          return false;
        }
      }

      // Check for logged-in indicators
      const isLoggedIn = await this.page.evaluate(() => {
        // Look for elements that only appear when logged in
        const profileLink = document.querySelector('a[href*="/direct/"]') ||
                           document.querySelector('svg[aria-label="Home"]') ||
                           document.querySelector('a[href="/"]');
        return !!profileLink;
      });

      if (isLoggedIn) {
        console.log('Already logged in');
        return true;
      }

      console.log('Could not verify login status');
      return false;
    } catch (error) {
      console.error('Error checking login:', error);
      return false;
    }
  }

  async navigateToReels(): Promise<boolean> {
    if (!this.page) return false;

    try {
      console.log('Navigating to Reels feed...');
      await this.page.goto('https://www.instagram.com/reels/', { waitUntil: 'networkidle', timeout: 30000 });
      await this.page.waitForTimeout(3000);

      // Wait for video elements to appear
      await this.page.waitForSelector('video', { timeout: 15000 });
      console.log('Reels feed loaded');
      return true;
    } catch (error) {
      console.error('Failed to navigate to Reels:', error);
      return false;
    }
  }

  async collectReels(targetCount: number): Promise<number> {
    if (!this.page) return 0;

    const existingCount = this.db.getReelsCountForDate(this.runDate);
    const remainingQuota = Math.max(0, targetCount - existingCount);

    if (remainingQuota === 0) {
      console.log(`Daily quota already met (${existingCount}/${targetCount} reels collected today)`);
      return 0;
    }

    console.log(`Collecting up to ${remainingQuota} reels (${existingCount} already collected today)`);

    let collected = 0;
    let consecutiveFailures = 0;
    const maxConsecutiveFailures = 5;

    while (collected < remainingQuota && consecutiveFailures < maxConsecutiveFailures) {
      try {
        const reelData = await this.extractCurrentReelData();

        if (reelData && reelData.source_url) {
          // Check for duplicate
          const isDuplicate = this.db.checkReelExists(reelData.source_url, this.runDate);

          if (!isDuplicate) {
            // Take screenshots
            const screenshots = await this.captureScreenshots();

            // Create reel record
            const reel: Reel = {
              run_id: this.runId,
              reel_date: this.runDate,
              source_url: reelData.source_url,
              creator_handle: reelData.creator_handle,
              caption_text: reelData.caption_text,
              visible_overlay_text: reelData.visible_overlay_text,
              collected_at: new Date().toISOString(),
              watch_duration_sec: this.config.watch_seconds_per_reel,
              screenshot_count: screenshots.length,
              transcript_text: null,
              raw_notes: null,
              processing_status: 'pending',
              is_duplicate: 0
            };

            const reelId = this.db.insertReel(reel);

            // Save screenshot records
            for (const screenshot of screenshots) {
              const screenshotRecord: ReelScreenshot = {
                reel_id: reelId,
                file_path: screenshot.path,
                captured_at: screenshot.timestamp,
                frame_index: screenshot.index,
                ocr_text: null
              };
              this.db.insertScreenshot(screenshotRecord);
            }

            collected++;
            this.reelsCollected++;
            this.db.updateRunReelsCollected(this.runId, this.reelsCollected);
            console.log(`Collected reel ${collected}/${remainingQuota}: ${reelData.creator_handle || 'unknown'}`);
            consecutiveFailures = 0;
          } else {
            console.log('Skipping duplicate reel');
          }
        } else {
          // Might be an ad - check and handle
          const isAd = await this.checkIfAd();
          if (isAd) {
            console.log('Ad detected, watching but not saving...');
            await this.page.waitForTimeout(this.config.watch_seconds_per_reel * 1000);
          } else {
            consecutiveFailures++;
            console.log(`Could not extract reel data (failure ${consecutiveFailures}/${maxConsecutiveFailures})`);
          }
        }

        // Watch the reel for configured duration
        await this.page.waitForTimeout(this.config.watch_seconds_per_reel * 1000);

        // Advance to next reel
        await this.advanceToNextReel();
        await this.page.waitForTimeout(2000); // Wait for next reel to load

      } catch (error) {
        consecutiveFailures++;
        console.error(`Error collecting reel (failure ${consecutiveFailures}/${maxConsecutiveFailures}):`, error);

        // Try to recover by advancing
        try {
          await this.advanceToNextReel();
          await this.page.waitForTimeout(2000);
        } catch {
          // If we can't even advance, something is seriously wrong
        }
      }
    }

    if (consecutiveFailures >= maxConsecutiveFailures) {
      console.log('Too many consecutive failures, stopping collection');
    }

    console.log(`Collection complete: ${collected} reels collected`);
    return collected;
  }

  private async extractCurrentReelData(): Promise<{
    source_url: string | null;
    creator_handle: string | null;
    caption_text: string | null;
    visible_overlay_text: string | null;
  } | null> {
    if (!this.page) return null;

    try {
      const data = await this.page.evaluate(() => {
        // Try to get the current URL which often contains the reel ID
        const url = window.location.href;

        // Extract creator handle - look for various selectors
        let creatorHandle: string | null = null;
        const handleSelectors = [
          'a[href^="/"] span',
          'header a[href^="/"]',
          '[class*="username"]',
          'a[role="link"][href^="/"]'
        ];

        for (const selector of handleSelectors) {
          const el = document.querySelector(selector);
          if (el && el.textContent) {
            const text = el.textContent.trim();
            if (text && !text.includes(' ') && text.length < 50) {
              creatorHandle = text.replace('@', '');
              break;
            }
          }
        }

        // Extract caption text
        let captionText: string | null = null;
        const captionSelectors = [
          '[class*="caption"]',
          'span[class*="Caption"]',
          'h1',
          'article span'
        ];

        for (const selector of captionSelectors) {
          const el = document.querySelector(selector);
          if (el && el.textContent && el.textContent.length > 10) {
            captionText = el.textContent.trim().substring(0, 2000);
            break;
          }
        }

        // Get any visible overlay text
        let overlayText: string | null = null;
        const overlayEls = document.querySelectorAll('[class*="overlay"] span, [class*="Overlay"] span');
        const overlayTexts: string[] = [];
        overlayEls.forEach(el => {
          if (el.textContent) {
            overlayTexts.push(el.textContent.trim());
          }
        });
        if (overlayTexts.length > 0) {
          overlayText = overlayTexts.join(' | ');
        }

        return {
          source_url: url,
          creator_handle: creatorHandle,
          caption_text: captionText,
          visible_overlay_text: overlayText
        };
      });

      // Clean up URL - try to extract just the reel URL
      if (data.source_url) {
        const reelMatch = data.source_url.match(/instagram\.com\/reels?\/([A-Za-z0-9_-]+)/);
        if (reelMatch) {
          data.source_url = `https://www.instagram.com/reel/${reelMatch[1]}/`;
        }
      }

      return data;
    } catch (error) {
      console.error('Error extracting reel data:', error);
      return null;
    }
  }

  private async checkIfAd(): Promise<boolean> {
    if (!this.page) return false;

    try {
      const isAd = await this.page.evaluate(() => {
        // Look for "Sponsored" text or ad indicators
        const bodyText = document.body.innerText.toLowerCase();
        const sponsoredIndicators = ['sponsored', 'paid partnership', 'ad'];
        return sponsoredIndicators.some(indicator => bodyText.includes(indicator));
      });
      return isAd;
    } catch {
      return false;
    }
  }

  private async captureScreenshots(): Promise<Array<{ path: string; timestamp: string; index: number }>> {
    if (!this.page) return [];

    const screenshots: Array<{ path: string; timestamp: string; index: number }> = [];
    const timestamp = Date.now();

    for (let i = 0; i < this.config.screenshots_per_reel; i++) {
      try {
        const filename = `reel_${timestamp}_${i}.png`;
        const filepath = path.join(this.config.screenshot_dir, filename);

        await this.page.screenshot({ path: filepath, fullPage: false });

        screenshots.push({
          path: filepath,
          timestamp: new Date().toISOString(),
          index: i
        });

        if (i < this.config.screenshots_per_reel - 1) {
          // Wait between screenshots to capture different frames
          await this.page.waitForTimeout(3000);
        }
      } catch (error) {
        console.error(`Error capturing screenshot ${i}:`, error);
      }
    }

    return screenshots;
  }

  private async advanceToNextReel(): Promise<void> {
    if (!this.page) return;

    try {
      // Try scrolling down to advance to next reel
      await this.page.keyboard.press('ArrowDown');

      // Alternative: swipe gesture simulation
      // await this.page.mouse.wheel(0, 500);
    } catch (error) {
      console.error('Error advancing to next reel:', error);
    }
  }

  async close(): Promise<void> {
    try {
      if (this.browser) {
        await this.browser.close();
        console.log('Browser closed');
      }
    } catch (error) {
      console.error('Error closing browser:', error);
    }
  }
}
