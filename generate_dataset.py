import json
import random
import scraper

print("Running scraper to fetch live leads...")
leads = scraper.scrape_truckerdb()
print(f"Successfully grabbed {len(leads)} leads.")

# A variety of natural, conversational pitch templates for the AI to learn
templates = [
    "Hi {officer}, saw your trucks are based out of {location}. Are you currently looking for dedicated dispatching for your routes?",
    "Hey {officer}, we are looking for reliable carriers operating near {location}. Do you need a dispatcher to keep {company}'s trucks moving?",
    "Hello {officer}. I noticed {company} has a fleet size of {fleet_size} in {location}. We specialize in keeping fleets like yours fully loaded. Open to a quick chat?",
    "Hi {officer} - I'm reaching out because we have excess freight moving through {location}. Can your {fleet_size} truck(s) handle more volume?",
    "Hey {officer}, just checking if {company} has capacity right now. We have dedicated lanes out of {location} that need a reliable carrier."
]

training_data = []

for lead in leads:
    # Pick a random template to ensure the AI learns variety
    template = random.choice(templates)
    
    # Fill in the blanks with the scraped data, converting to Title Case for natural reading
    completion = template.format(
        officer=lead["officer"].title(),
        location=lead["location"].title(),
        company=lead["company"].title(),
        fleet_size=lead["fleet_size"]
    )
    
    # Create the exact prompt format your AI expects based on your Colab script
    prompt = f"Officer: {lead['officer']}, Location: {lead['location']}"
    
    # Append as a dictionary
    training_data.append({
        "prompt": prompt,
        "completion": completion
    })

# Save to the JSONL format
with open("train.jsonl", "w") as f:
    for item in training_data:
        f.write(json.dumps(item) + "\n")

print("Successfully generated 50-line 'train.jsonl' dataset!")