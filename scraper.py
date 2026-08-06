from playwright.sync_api import sync_playwright

def scrape_truckerdb():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False) # Set to True once it works perfectly
        page = browser.new_page()
        
        # You will need to handle the login process here first
        page.goto("https://www.truckerdb.com/dashboard/sample")
        page.wait_for_selector(".table-row-class") # Update with actual CSS class
        
        leads = []
        rows = page.query_selector_all("tr.data-row") # Update with actual row selector
        
        for row in rows:
            officer = row.query_selector(".officer-col").inner_text()
            email = row.query_selector(".email-col").inner_text()
            location = row.query_selector(".location-col").inner_text()
            
            leads.append({
                "officer": officer,
                "email": email,
                "location": location
            })
            
        browser.close()
        return leads