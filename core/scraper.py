from playwright.sync_api import sync_playwright


def scrape_truckerdb():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False) 
        
        context = browser.new_context(storage_state="auth/playwright_auth.json")
        page = context.new_page()
        
        print("Navigating directly to the TruckerDB dashboard...")
        page.goto("https://www.truckerdb.com/dashboard/sample", wait_until="domcontentloaded")

        
        try:
            page.wait_for_selector("table, tbody tr, div[role='row']", timeout=10000)
        except Exception:
            print("Table selector not immediately found. Dumping page content to inspect...")

        leads = []
        rows = page.query_selector_all("table tbody tr")
        
        if not rows:
            rows = page.query_selector_all("div[role='row']")

        print(f"Found {len(rows)} carrier rows on page.")

        
        for row in rows:
            cells = [cell.inner_text().strip() for cell in row.query_selector_all("td, div[role='cell']")]
            
            if len(cells) >= 9:
                email = cells[4]
                
                if "@" in email:
                    leads.append({
                        "officer": cells[3],
                        "email": email.lower(),
                        "location": cells[6],
                        "company": cells[0],
                        "fleet_size": cells[8]
                    })

        browser.close()
        return leads

if __name__ == "__main__":
    extracted = scrape_truckerdb()
    print(f"Successfully extracted {len(extracted)} valid leads with emails.")
    for lead in extracted[:3]: 
        print(lead)