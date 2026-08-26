"""
LeadScraperTool: refactor of the original core/scraper.py into the tool
interface. Behavior preserved (Playwright + saved storage_state), but:
  - the storage_state path comes from an env var, not a path committed to git
  - selectors are unchanged from the original but isolated behind execute()
    so the agent core never talks to Playwright directly
"""
import os
from app.tools.base import Tool


class LeadScraperTool(Tool):
    name = "scraper"

    def __init__(self, auth_state_path=None, target_url=None, headless=True):
        self.auth_state_path = auth_state_path or os.environ.get(
            "SCRAPER_AUTH_STATE_PATH", "auth/playwright_auth.json"
        )
        self.target_url = target_url or os.environ.get(
            "SCRAPER_TARGET_URL", "https://www.truckerdb.com/dashboard/sample"
        )
        self.headless = headless

    def execute(self, max_leads=50):
        from playwright.sync_api import sync_playwright  # imported lazily; optional dependency

        if not os.path.exists(self.auth_state_path):
            raise FileNotFoundError(
                f"No saved auth state at {self.auth_state_path}. "
                f"Run the auth setup script first to generate a fresh session "
                f"(the previous one committed to git must be treated as compromised)."
            )

        leads = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            context = browser.new_context(storage_state=self.auth_state_path)
            page = context.new_page()
            page.goto(self.target_url, wait_until="domcontentloaded")

            try:
                page.wait_for_selector("table, tbody tr, div[role='row']", timeout=10000)
            except Exception:
                pass

            rows = page.query_selector_all("table tbody tr") or page.query_selector_all("div[role='row']")

            for row in rows[:max_leads]:
                cells = [c.inner_text().strip() for c in row.query_selector_all("td, div[role='cell']")]
                if len(cells) >= 9 and "@" in cells[4]:
                    leads.append({
                        "officer": cells[3],
                        "email": cells[4].lower(),
                        "location": cells[6],
                        "company": cells[0],
                        "fleet_size": cells[8],
                    })

            browser.close()

        return leads
