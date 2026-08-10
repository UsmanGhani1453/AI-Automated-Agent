from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests

app = FastAPI(title="Local Dispatch AI Service")

class LeadRequest(BaseModel):
    officer: str
    location: str

@app.post("/generate-email")
def generate_email(lead: LeadRequest):
    try:
        prompt = f"""Below is an instruction that describes a task, paired with an input that provides further context. Write a response that appropriately completes the request.

### Instruction:
Write a personalized dispatching offer email.

### Input:
Officer: {lead.officer}, Location: {lead.location}

### Response:"""

        # Send request to your local Ollama server running gemma2:2b
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "gemma2:2b",
                "prompt": prompt,
                "stream": False
            }
        )
        
        result = response.json()
        
        return {
            "status": "success",
            "officer": lead.officer,
            "generated_email": result.get("response", "").strip()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))