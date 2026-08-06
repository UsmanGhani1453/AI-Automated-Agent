import requests
from bs4 import BeautifulSoup
import openai # Or your preferred AI endpoint
import time

# Configure your API key
# openai.api_key = "YOUR_API_KEY"

def scrape_truck_leads(directory_url):
    """Scrapes driver/owner data f  rom a target website."""
    print(f"Scraping leads from {directory_url}...")
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    
    try:
        response = requests.get(directory_url, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        leads = []
        # Update these selectors based on the actual website's HTML structure
        for card in soup.find_all('div', class_='trucker-profile-card'):
            lead = {
                "name": card.find('h2', class_='owner-name').text.strip(),
                "company": card.find('p', class_='company-name').text.strip(),
                "fleet_size": card.find('span', class_='fleet-size').text.strip(),
                "email": card.find('a', class_='contact-email')['href'].replace('mailto:', '')
            }
            leads.append(lead)
            
        return leads
    
    except Exception as e:
        print(f"Error scraping data: {e}")
        return []

def generate_personalized_message(lead_data):
    """Passes the scraped data to the LLM to write a unique email."""
    print(f"Generating message for {lead_data['name']}...")
    
    prompt = f"""
    Write a short, highly personalized cold email to a trucking company owner.
    Do not sound like a robot. Keep it under 4 sentences.
    
    Data:
    - Name: {lead_data['name']}
    - Company: {lead_data['company']}
    - Fleet Size: {lead_data['fleet_size']}
    
    The goal is to ask if they have capacity for new dedicated freight lanes.
    """

    try:
        # Update this call to match your current API endpoint syntax
        response = openai.chat.completions.create(
            model="gpt-4o", # Or Gemini/Claude
            messages=[
                {"role": "system", "content": "You are a logistics partnership manager."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7 # Slight variance helps bypass spam filters
        )
        return response.choices[0].message.content
    
    except Exception as e:
        print(f"Error generating message: {e}")
        return None

def main():
    # Replace with the actual URL you want to target
    target_url = "https://example-trucking-directory.com/carriers"
    
    # 1. Get the data
    truck_leads = scrape_truck_leads(target_url)
    
    if not truck_leads:
        print("No leads found. Check your HTML selectors.")
        return

    # 2. Process each lead
    for lead in truck_leads:
        message = generate_personalized_message(lead)
        
        if message:
            print("-" * 40)
            print(f"To: {lead['email']}")
            print(f"Subject: Quick question for {lead['company']}")
            print(f"Body:\n{message}\n")
            
            # Here you would call your existing email dispatch function
            # send_email(lead['email'], subject, message)
            
            # Pause to avoid rate limits and spam flags
            time.sleep(5) 

if __name__ == "__main__":
    main()