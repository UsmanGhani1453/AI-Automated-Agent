from playwright.sync_api import sync_playwright

def login_and_save_state():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        
        print("Opening TruckerDB. Please log in manually...")
        # Update this URL to the actual TruckerDB login page
        page.goto("https://www.truckerdb.com") 
        
        # The script pauses and gives you 60 seconds to log in.
        # It waits until the URL changes to the dashboard.
        try:
            page.wait_for_url("**/dashboard**", timeout=60000)
            print("Login detected! Saving session state...")
            
            # This saves your cookies and local storage
            context.storage_state(path="playwright_auth.json") 
            print("Session successfully saved to 'playwright_auth.json'.")
            
        except Exception as e:
            print("Did not reach the dashboard in time, or an error occurred.")
            print(e)
            
        browser.close()

if __name__ == "__main__":
    login_and_save_state()