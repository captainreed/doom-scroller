import json
import os
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

from anthropic import Anthropic

from .config import Config
from .database import DatabaseManager, Reel, ReelAnalysis, Claim, ReelScreenshot

# Try to import OCR - optional dependency
try:
    import pytesseract
    from PIL import Image
    HAS_OCR = True
except ImportError:
    HAS_OCR = False


class ReelAnalyzer:
    def __init__(self, config: Config, db: DatabaseManager):
        self.config = config
        self.db = db
        self.client = Anthropic(
            api_key=config.llm.get_api_key(),
            base_url=config.llm.api_base_url if config.llm.api_base_url != "https://api.anthropic.com" else None
        )
        self.prompts = self._load_prompts()

    def _load_prompts(self) -> Dict[str, str]:
        """Load prompt templates from files."""
        prompts_dir = Path(self.config.project_root) / "shared" / "prompts"
        prompts = {}

        prompt_files = {
            "summary": "reel_summary.txt",
            "claims": "claim_extraction.txt",
            "report": "report_compile.txt"
        }

        for key, filename in prompt_files.items():
            filepath = prompts_dir / filename
            if filepath.exists():
                prompts[key] = filepath.read_text()
            else:
                print(f"Warning: Prompt file not found: {filepath}")
                prompts[key] = ""

        return prompts

    def extract_ocr_text(self, screenshot_path: str) -> str:
        """Extract text from screenshot using OCR."""
        if not HAS_OCR:
            return ""

        try:
            if not os.path.exists(screenshot_path):
                return ""

            image = Image.open(screenshot_path)
            text = pytesseract.image_to_string(image)
            return text.strip()
        except Exception as e:
            print(f"OCR error for {screenshot_path}: {e}")
            return ""

    def analyze_reel(self, reel: Reel) -> bool:
        """Analyze a single reel and save results."""
        print(f"Analyzing reel {reel.id}: {reel.creator_handle or 'unknown'}")

        try:
            # Gather all text content
            text_content = self._gather_text_content(reel)

            if not text_content.strip():
                print(f"  No text content found for reel {reel.id}")
                self.db.update_reel_processing_status(reel.id, "failed")
                return False

            # Get summary and analysis
            analysis_result = self._get_llm_analysis(text_content)
            if not analysis_result:
                print(f"  LLM analysis failed for reel {reel.id}")
                self.db.update_reel_processing_status(reel.id, "failed")
                return False

            # Save analysis
            analysis = ReelAnalysis(
                id=None,
                reel_id=reel.id,
                short_summary=analysis_result.get("short_summary"),
                main_points=json.dumps(analysis_result.get("main_points", [])),
                topic_tags=json.dumps(analysis_result.get("topic_tags", [])),
                category_primary=analysis_result.get("category_primary"),
                category_secondary=analysis_result.get("category_secondary"),
                is_news_related=1 if analysis_result.get("is_news_related") else 0,
                is_funny=1 if analysis_result.get("is_funny") else 0,
                is_educational=1 if analysis_result.get("is_educational") else 0,
                is_socially_important=1 if analysis_result.get("is_socially_important") else 0,
                contains_speculation=1 if analysis_result.get("contains_speculation") else 0,
                contains_factual_claims=1 if analysis_result.get("contains_factual_claims") else 0,
                funny_score=analysis_result.get("funny_score"),
                educational_score=analysis_result.get("educational_score"),
                social_importance_score=analysis_result.get("social_importance_score"),
                news_relevance_score=analysis_result.get("news_relevance_score"),
                overall_noteworthiness_score=analysis_result.get("overall_noteworthiness_score"),
                save_flag=0,
                analysis_created_at=datetime.now().isoformat()
            )
            self.db.save_analysis(analysis)

            # Extract and save claims
            claims_result = self._extract_claims(text_content)
            for claim_data in claims_result.get("claims", []):
                claim = Claim(
                    id=None,
                    reel_id=reel.id,
                    claim_text=claim_data.get("claim_text", ""),
                    claim_type=claim_data.get("claim_type", "unknown"),
                    confidence=claim_data.get("confidence"),
                    appears_unsubstantiated=1 if claim_data.get("appears_unsubstantiated") else 0,
                    support_status=claim_data.get("support_status", "unknown"),
                    reasoning=claim_data.get("reasoning"),
                    created_at=datetime.now().isoformat()
                )
                self.db.save_claim(claim)

            # Mark as processed
            self.db.update_reel_processing_status(reel.id, "processed")
            print(f"  Analysis complete for reel {reel.id}")
            return True

        except Exception as e:
            print(f"  Error analyzing reel {reel.id}: {e}")
            self.db.update_reel_processing_status(reel.id, "failed")
            return False

    def _gather_text_content(self, reel: Reel) -> str:
        """Gather all available text content for a reel."""
        parts = []

        if reel.creator_handle:
            parts.append(f"Creator: @{reel.creator_handle}")

        if reel.caption_text:
            parts.append(f"Caption: {reel.caption_text}")

        if reel.visible_overlay_text:
            parts.append(f"Overlay Text: {reel.visible_overlay_text}")

        if reel.transcript_text:
            parts.append(f"Transcript: {reel.transcript_text}")

        # Get OCR text from screenshots
        screenshots = self.db.get_screenshots_for_reel(reel.id)
        for screenshot in screenshots:
            ocr_text = screenshot.ocr_text
            if not ocr_text and HAS_OCR:
                # Run OCR if not already done
                ocr_text = self.extract_ocr_text(screenshot.file_path)
                if ocr_text:
                    self.db.update_screenshot_ocr(screenshot.id, ocr_text)

            if ocr_text:
                parts.append(f"OCR Text (screenshot {screenshot.frame_index}): {ocr_text}")

        return "\n\n".join(parts)

    def _get_llm_analysis(self, text_content: str) -> Optional[Dict[str, Any]]:
        """Get analysis from LLM."""
        try:
            prompt = self.prompts.get("summary", "")
            if not prompt:
                prompt = "Analyze this Instagram Reel content and return JSON with summary, categories, and scores."

            response = self.client.messages.create(
                model=self.config.llm.model,
                max_tokens=self.config.llm.max_tokens,
                messages=[
                    {
                        "role": "user",
                        "content": f"{prompt}\n\n---\n\nReel Content:\n{text_content}"
                    }
                ]
            )

            response_text = response.content[0].text.strip()

            # Try to parse JSON from response
            # Handle case where response might have markdown code blocks
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0]

            return json.loads(response_text)

        except json.JSONDecodeError as e:
            print(f"  JSON parse error: {e}")
            return None
        except Exception as e:
            print(f"  LLM error: {e}")
            return None

    def _extract_claims(self, text_content: str) -> Dict[str, Any]:
        """Extract claims from reel content."""
        try:
            prompt = self.prompts.get("claims", "")
            if not prompt:
                prompt = "Extract factual claims from this content and return JSON."

            response = self.client.messages.create(
                model=self.config.llm.model,
                max_tokens=self.config.llm.max_tokens,
                messages=[
                    {
                        "role": "user",
                        "content": f"{prompt}\n\n---\n\nReel Content:\n{text_content}"
                    }
                ]
            )

            response_text = response.content[0].text.strip()

            # Handle markdown code blocks
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0]

            return json.loads(response_text)

        except Exception as e:
            print(f"  Claims extraction error: {e}")
            return {"claims": []}

    def analyze_pending_reels(self) -> int:
        """Analyze all pending reels."""
        pending_reels = self.db.get_pending_reels()
        print(f"Found {len(pending_reels)} pending reels to analyze")

        success_count = 0
        for reel in pending_reels:
            if self.analyze_reel(reel):
                success_count += 1

        print(f"Successfully analyzed {success_count}/{len(pending_reels)} reels")
        return success_count
