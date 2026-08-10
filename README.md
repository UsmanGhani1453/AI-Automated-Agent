# AI Automated Agent (Freight Dispatching)

## Overview
This project is an automated lead-generation and outreach tool designed for freight dispatching. It performs three core functions:
1. **Lead Scraping:** Uses Playwright to extract live carrier leads (Officer Name, Company, Fleet Size, Location, Email) from TruckerDB.
2. **AI Email Generation:** Sends the scraped context to a local FastAPI backend running the `gemma2:2b` model via Ollama to generate highly personalized, formatted outreach emails.
3. **Automated Sending:** Dispatches the generated emails directly to the carriers via Gmail SMTP.

---

## Folder Structure

```text
AI AUTOMATED AGENT/
│
├── core/                       # Main executable scripts
│   ├── outreach_pipeline.py    # Main coordinator script
│   ├── my_api.py               # FastAPI local AI backend
│   └── scraper.py              # Playwright web scraper
│
├── auth/                       # Authentication related files
│   ├── auth_setup.py           # Script to capture login state
│   └── playwright_auth.json    # Saved session cookies
│
├── .env                        # Environment variables (SENDER_EMAIL, etc.)
├── .gitignore                  # Git ignore rules 
├── requirements.txt            # Python dependencies
└── README.md                   # Project documentation
```

---

## Prerequisites & Setup

1. **Local AI Model:** Ensure you have [Ollama](https://ollama.com/) installed and running locally with the Gemma 2 (2B) model.
   ```bash
   ollama run gemma2:2b
   ```
2. **Environment Variables:** You must have a `.env` file in the root directory containing your Gmail address and 16-character Google App Password.
3. **Virtual Environment:** Ensure your `venv` is active and dependencies from `requirements.txt` are installed.
   ```bash
   source venv/bin/activate
   pip install -r requirements.txt
   ```
4. **Authentication:** If your session expires, run `python auth/auth_setup.py` to log in to TruckerDB and refresh your `playwright_auth.json` file.

---

## How to Run the Pipeline

Because this project relies on a local AI backend, you must run it using **two separate terminal windows**. Ensure your virtual environment (`venv`) is activated in both.

### Terminal 1: Start the Local AI Server
This starts the FastAPI server that generates the emails.
```bash
uvicorn core.my_api:app --reload --port 8000
```
*(Leave this running in the background. It should state `Uvicorn running on http://127.0.0.1:8000`)*

### Terminal 2: Run the Outreach Coordinator
This script will trigger the scraper, request the emails from the API, and send them out.
```bash
python core/outreach_pipeline.py
```
