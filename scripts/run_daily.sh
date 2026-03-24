#!/bin/bash
# Instagram Reels Daily Digest - Daily Run Script (Bash)
# This script runs the full daily pipeline:
# 1. Collect reels using the browser agent
# 2. Analyze collected reels
# 3. Generate daily report

set -e

# Get script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "=== Instagram Reels Daily Digest ==="
echo "Project Root: $PROJECT_ROOT"
echo ""

# Step 1: Run browser agent to collect reels
echo "=== Step 1: Collecting Reels ==="
cd "$PROJECT_ROOT/browser-agent"

if npm run dev; then
    echo "Reel collection complete!"
else
    echo "Warning: Browser agent encountered an error. Continuing with analysis..."
fi

echo ""

# Step 2: Run analysis and report generation
echo "=== Step 2: Analyzing Reels & Generating Report ==="
cd "$PROJECT_ROOT/analysis-worker"

python -m app.main run-daily

echo ""
echo "=== Daily Pipeline Complete ==="

# Return to project root
cd "$PROJECT_ROOT"
