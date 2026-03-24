import json
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

from anthropic import Anthropic

from .config import Config
from .database import DatabaseManager


class ReportGenerator:
    def __init__(self, config: Config, db: DatabaseManager):
        self.config = config
        self.db = db
        self.client = Anthropic(
            api_key=config.llm.get_api_key(),
            base_url=config.llm.api_base_url if config.llm.api_base_url != "https://api.anthropic.com" else None
        )
        self.report_prompt = self._load_report_prompt()

    def _load_report_prompt(self) -> str:
        """Load report compilation prompt."""
        prompt_path = Path(self.config.project_root) / "shared" / "prompts" / "report_compile.txt"
        if prompt_path.exists():
            return prompt_path.read_text()
        return ""

    def generate_report(self, date: str) -> Optional[str]:
        """Generate daily report for a specific date."""
        print(f"Generating report for {date}...")

        # Get all analyses and claims for the date
        analyses = self.db.get_analyses_for_date(date)
        claims = self.db.get_claims_for_date(date)

        if not analyses:
            print(f"No analyzed reels found for {date}")
            return None

        print(f"Found {len(analyses)} analyzed reels and {len(claims)} claims")

        # Prepare data for LLM
        report_data = self._prepare_report_data(analyses, claims)

        # Generate report using LLM
        report_content = self._generate_with_llm(date, report_data)

        if not report_content:
            # Fall back to structured report without LLM
            report_content = self._generate_structured_report(date, analyses, claims)

        # Save report
        report_path = self._save_report(date, report_content)

        # Save to database
        self.db.save_daily_report(
            report_date=date,
            run_id=None,  # Could get from reels if needed
            total_reels=len(analyses),
            markdown_path=report_path,
            text_path=None,
            summary_blob=report_content[:5000] if report_content else None
        )

        print(f"Report saved to: {report_path}")
        return report_path

    def _prepare_report_data(
        self, analyses: List[Dict[str, Any]], claims: List[Dict[str, Any]]
    ) -> str:
        """Prepare data summary for LLM report generation."""
        lines = ["## Analyzed Reels Summary\n"]

        for i, analysis in enumerate(analyses, 1):
            lines.append(f"### Reel {i}")
            lines.append(f"- Creator: @{analysis.get('creator_handle', 'unknown')}")
            lines.append(f"- URL: {analysis.get('source_url', 'N/A')}")
            lines.append(f"- Summary: {analysis.get('short_summary', 'N/A')}")
            lines.append(f"- Category: {analysis.get('category_primary', 'N/A')}")

            # Parse topic tags
            try:
                tags = json.loads(analysis.get('topic_tags', '[]'))
                lines.append(f"- Topics: {', '.join(tags)}")
            except:
                pass

            # Flags
            flags = []
            if analysis.get('is_funny'): flags.append('funny')
            if analysis.get('is_educational'): flags.append('educational')
            if analysis.get('is_news_related'): flags.append('news')
            if analysis.get('is_socially_important'): flags.append('socially important')
            if flags:
                lines.append(f"- Flags: {', '.join(flags)}")

            # Scores
            scores = []
            if analysis.get('funny_score'):
                scores.append(f"funny: {analysis['funny_score']:.2f}")
            if analysis.get('educational_score'):
                scores.append(f"educational: {analysis['educational_score']:.2f}")
            if analysis.get('social_importance_score'):
                scores.append(f"social: {analysis['social_importance_score']:.2f}")
            if analysis.get('news_relevance_score'):
                scores.append(f"news: {analysis['news_relevance_score']:.2f}")
            if scores:
                lines.append(f"- Scores: {', '.join(scores)}")

            lines.append("")

        if claims:
            lines.append("\n## Extracted Claims\n")
            for claim in claims:
                lines.append(f"- **Claim**: {claim.get('claim_text', 'N/A')}")
                lines.append(f"  - Type: {claim.get('claim_type', 'unknown')}")
                lines.append(f"  - Unsubstantiated: {'Yes' if claim.get('appears_unsubstantiated') else 'No'}")
                lines.append(f"  - Creator: @{claim.get('creator_handle', 'unknown')}")
                lines.append(f"  - URL: {claim.get('source_url', 'N/A')}")
                if claim.get('reasoning'):
                    lines.append(f"  - Reasoning: {claim['reasoning']}")
                lines.append("")

        return "\n".join(lines)

    def _generate_with_llm(self, date: str, report_data: str) -> Optional[str]:
        """Generate report using LLM."""
        try:
            prompt = self.report_prompt or "Compile a daily digest report from the following analyzed reels."

            response = self.client.messages.create(
                model=self.config.llm.model,
                max_tokens=self.config.llm.max_tokens,
                messages=[
                    {
                        "role": "user",
                        "content": f"{prompt}\n\nDate: {date}\n\n{report_data}"
                    }
                ]
            )

            return response.content[0].text.strip()

        except Exception as e:
            print(f"LLM report generation error: {e}")
            return None

    def _generate_structured_report(
        self, date: str, analyses: List[Dict[str, Any]], claims: List[Dict[str, Any]]
    ) -> str:
        """Generate a structured report without LLM (fallback)."""
        lines = [
            f"# Daily Reel Digest - {date}",
            "",
            "## Summary",
            f"- Total reels processed: {len(analyses)}",
        ]

        # Count categories
        funny_count = sum(1 for a in analyses if a.get('is_funny'))
        edu_count = sum(1 for a in analyses if a.get('is_educational'))
        social_count = sum(1 for a in analyses if a.get('is_socially_important'))
        news_count = sum(1 for a in analyses if a.get('is_news_related'))
        unsub_claims = [c for c in claims if c.get('appears_unsubstantiated')]

        lines.extend([
            f"- Funny picks: {funny_count}",
            f"- Educational picks: {edu_count}",
            f"- Socially important picks: {social_count}",
            f"- News-related reels: {news_count}",
            f"- Potentially unsubstantiated claims: {len(unsub_claims)}",
            "",
            "## Top Themes",
        ])

        # Collect all topics
        all_topics = []
        for analysis in analyses:
            try:
                tags = json.loads(analysis.get('topic_tags', '[]'))
                all_topics.extend(tags)
            except:
                pass

        # Count and sort topics
        topic_counts = {}
        for topic in all_topics:
            topic_counts[topic] = topic_counts.get(topic, 0) + 1
        top_topics = sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)[:5]

        for topic, count in top_topics:
            lines.append(f"- {topic} ({count} reels)")

        lines.append("")

        # Unsubstantiated claims section
        if unsub_claims:
            lines.extend(["## Potentially Unsubstantiated Claims", ""])
            for claim in unsub_claims:
                lines.extend([
                    f"### {claim.get('claim_text', 'Unknown claim')[:100]}",
                    f"- Creator: @{claim.get('creator_handle', 'unknown')}",
                    f"- Reel URL: {claim.get('source_url', 'N/A')}",
                    f"- Why flagged: {claim.get('reasoning', 'Presented without supporting evidence')}",
                    ""
                ])

        # Funny picks
        funny_reels = sorted(
            [a for a in analyses if a.get('is_funny')],
            key=lambda x: x.get('funny_score', 0) or 0,
            reverse=True
        )[:5]

        if funny_reels:
            lines.extend(["## Funny Picks", ""])
            for reel in funny_reels:
                lines.extend([
                    f"### @{reel.get('creator_handle', 'unknown')}",
                    f"- Summary: {reel.get('short_summary', 'N/A')}",
                    f"- Link: {reel.get('source_url', 'N/A')}",
                    ""
                ])

        # Educational picks
        edu_reels = sorted(
            [a for a in analyses if a.get('is_educational')],
            key=lambda x: x.get('educational_score', 0) or 0,
            reverse=True
        )[:5]

        if edu_reels:
            lines.extend(["## Educational Picks", ""])
            for reel in edu_reels:
                lines.extend([
                    f"### @{reel.get('creator_handle', 'unknown')}",
                    f"- Summary: {reel.get('short_summary', 'N/A')}",
                    f"- Link: {reel.get('source_url', 'N/A')}",
                    ""
                ])

        # Socially important picks
        social_reels = sorted(
            [a for a in analyses if a.get('is_socially_important')],
            key=lambda x: x.get('social_importance_score', 0) or 0,
            reverse=True
        )[:5]

        if social_reels:
            lines.extend(["## Socially Important Picks", ""])
            for reel in social_reels:
                lines.extend([
                    f"### @{reel.get('creator_handle', 'unknown')}",
                    f"- Summary: {reel.get('short_summary', 'N/A')}",
                    f"- Link: {reel.get('source_url', 'N/A')}",
                    ""
                ])

        # Notable reels (top overall)
        notable_reels = sorted(
            analyses,
            key=lambda x: x.get('overall_noteworthiness_score', 0) or 0,
            reverse=True
        )[:10]

        lines.extend(["## Notable Reels", ""])
        for reel in notable_reels:
            try:
                tags = json.loads(reel.get('topic_tags', '[]'))
                tags_str = ', '.join(tags)
            except:
                tags_str = ''

            lines.extend([
                f"### @{reel.get('creator_handle', 'unknown')}",
                f"- Summary: {reel.get('short_summary', 'N/A')}",
                f"- Tags: {tags_str}",
                f"- Link: {reel.get('source_url', 'N/A')}",
                ""
            ])

        return "\n".join(lines)

    def _save_report(self, date: str, content: str) -> str:
        """Save report to file."""
        filename = f"daily_reel_digest_{date}.md"
        filepath = os.path.join(self.config.report_output_dir, filename)

        os.makedirs(self.config.report_output_dir, exist_ok=True)

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)

        return filepath
