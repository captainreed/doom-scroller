import * as fs from 'fs';
import * as path from 'path';

export interface LLMConfig {
  provider: string;
  api_key_file: string;
  api_base_url: string;
  model: string;
  max_tokens: number;
}

export interface Config {
  daily_reel_target: number;
  report_output_dir: string;
  watch_seconds_per_reel: number;
  screenshots_per_reel: number;
  browser_profile_dir: string;
  database_path: string;
  headless: boolean;
  max_run_minutes: number;
  skip_if_already_completed_today: boolean;
  llm: LLMConfig;
  screenshot_dir: string;
  log_dir: string;
}

const DEFAULT_CONFIG: Config = {
  daily_reel_target: 50,
  report_output_dir: './data/reports',
  watch_seconds_per_reel: 18,
  screenshots_per_reel: 2,
  browser_profile_dir: './data/browser-profile',
  database_path: './data/app.db',
  headless: false,
  max_run_minutes: 180,
  skip_if_already_completed_today: true,
  llm: {
    provider: 'anthropic',
    api_key_file: './api key.txt',
    api_base_url: 'https://api.anthropic.com',
    model: 'claude-sonnet-4-20250514',
    max_tokens: 4096
  },
  screenshot_dir: './data/screenshots',
  log_dir: './data/logs'
};

export function loadConfig(projectRoot: string): Config {
  const configPath = path.join(projectRoot, 'shared', 'config', 'config.json');

  try {
    const configContent = fs.readFileSync(configPath, 'utf-8');
    const userConfig = JSON.parse(configContent);

    // Merge with defaults
    const config: Config = {
      ...DEFAULT_CONFIG,
      ...userConfig,
      llm: {
        ...DEFAULT_CONFIG.llm,
        ...(userConfig.llm || {})
      }
    };

    // Resolve relative paths to absolute
    config.report_output_dir = resolvePath(projectRoot, config.report_output_dir);
    config.browser_profile_dir = resolvePath(projectRoot, config.browser_profile_dir);
    config.database_path = resolvePath(projectRoot, config.database_path);
    config.screenshot_dir = resolvePath(projectRoot, config.screenshot_dir);
    config.log_dir = resolvePath(projectRoot, config.log_dir);
    config.llm.api_key_file = resolvePath(projectRoot, config.llm.api_key_file);

    // Ensure directories exist
    ensureDir(config.report_output_dir);
    ensureDir(config.browser_profile_dir);
    ensureDir(config.screenshot_dir);
    ensureDir(config.log_dir);
    ensureDir(path.dirname(config.database_path));

    return config;
  } catch (error) {
    console.warn('Could not load config file, using defaults:', error);
    return DEFAULT_CONFIG;
  }
}

function resolvePath(projectRoot: string, filePath: string): string {
  if (path.isAbsolute(filePath)) {
    return filePath;
  }
  return path.join(projectRoot, filePath);
}

function ensureDir(dirPath: string): void {
  if (!fs.existsSync(dirPath)) {
    fs.mkdirSync(dirPath, { recursive: true });
  }
}

export function getProjectRoot(): string {
  // Navigate up from browser-agent/src to project root
  return path.resolve(__dirname, '..', '..');
}
