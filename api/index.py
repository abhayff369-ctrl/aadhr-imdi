# api/index.py - Vercel serverless function
from fastapi import FastAPI, Query, HTTPException, Header, Depends
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
import requests
from bs4 import BeautifulSoup
import re
import time
import os
import json

app = FastAPI(title="Aadhar Ration Scraper API", owner="Abhay Singh", version="2.0")

# ========== MULTI-KEY AUTHENTICATION ==========
# Store keys in Vercel Environment Variables: API_KEYS=key1,key2,key3
VALID_API_KEYS = os.environ.get("API_KEYS", "test-key-123,dev-key-456").split(",")
VALID_API_KEYS = [k.strip() for k in VALID_API_KEYS]

def verify_api_key(api_key: str = Header(..., alias="X-API-Key")):
    """Verify API key from header X-API-Key"""
    if api_key not in VALID_API_KEYS:
        raise HTTPException(status_code=401, detail="Invalid or missing API Key")
    return api_key

# ========== SESSION MANAGEMENT ==========
def get_session():
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Mobile Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
        "Referer": "https://impds.nic.in/impdsdeduplication/search"
    })
    return session

# ========== SCRAPING FUNCTION ==========
def scrape_ration_by_aadhar(aadhar_number: str, session: requests.Session) -> Dict[str, Any]:
    """
    Scrape ration card details linked to an Aadhar number.
    """
    search_url = "https://impds.nic.in/impdsdeduplication/searchRationByAadhar"
    
    # Get initial CSRF from home page
    home_resp = session.get("https://impds.nic.in/impdsdeduplication/search")
    soup = BeautifulSoup(home_resp.text, 'html.parser')
    
    csrf_token = None
    for name in ['csrf_token', '_token', 'csrfmiddlewaretoken', 'authenticity_token']:
        inp = soup.find('input', {'name': name})
        if inp:
            csrf_token = inp.get('value')
            break
    
    payload = {
        "aadharNumber": aadhar_number,
        "csrf_token": csrf_token or "",
        "action": "search"
    }
    
    response = session.post(search_url, data=payload)
    
    if response.status_code != 200:
        return {"error": f"HTTP {response.status_code}", "aadhar": aadhar_number}
    
    soup = BeautifulSoup(response.text, 'html.parser')
    
    ration_data = {
        "aadhar": aadhar_number,
        "ration_card_number": None,
        "card_type": None,
        "family_members": [],
        "entitlements": {},
        "status": None,
        "scraped_at": time.time()
    }
    
    # Extract data (update selectors after inspecting actual page)
    card_num_elem = soup.select_one(".ration-card-number, .card-number, #rationCardNo")
    if card_num_elem:
        ration_data["ration_card_number"] = card_num_elem.text.strip()
    
    card_type_elem = soup.select_one(".card-type, .type")
    if card_type_elem:
        ration_data["card_type"] = card_type_elem.text.strip()
    
    # Family members table
    members_table = soup.find("table", {"class": "family-members"})
    if members_table:
        rows = members_table.find_all("tr")[1:]
        for row in rows:
            cols = row.find_all("td")
            if len(cols) >= 3:
                ration_data["family_members"].append({
                    "name": cols[0].text.strip(),
                    "relation": cols[1].text.strip(),
                    "age": cols[2].text.strip()
                })
    
    # Entitlements
    entitle_div = soup.find("div", {"class": "entitlements"})
    if entitle_div:
        items = entitle_div.find_all("li")
        for item in items:
            text = item.text.strip()
            if ":" in text:
                k, v = text.split(":", 1)
                ration_data["entitlements"][k.strip()] = v.strip()
    
    status_elem = soup.find("div", {"class": "status"}) or soup.find("div", {"class": "alert"})
    if status_elem:
        ration_data["status"] = status_elem.text.strip()
    
    return ration_data

# ========== API ENDPOINTS ==========
@app.get("/")
def root():
    return {
        "name": "Aadhar Ration Scraper API",
        "developer": "Abhay Singh",
        "version": "2.0",
        "endpoints": [
            "GET /scrape/ration?adhar=123456789012",
            "GET /scrape/bulk?aadhars=123456789012,234567890123",
            "GET /keys/list - List available keys (admin)",
            "GET /health"
        ],
        "auth": "Header X-API-Key"
    }

@app.get("/scrape/ration")
def scrape_ration(
    api_key: str = Depends(verify_api_key),
    aadhar: str = Query(..., description="12-digit Aadhar number", regex="^\d{12}$"),
    format: str = Query("json", description="Output format: json or text")
) -> Dict[str, Any]:
    """Scrape ration card details using Aadhar number"""
    if not re.match(r"^\d{12}$", aadhar):
        raise HTTPException(status_code=400, detail="Aadhar must be 12 digits")
    
    try:
        session = get_session()
        result = scrape_ration_by_aadhar(aadhar, session)
        
        if format == "text":
            text_out = f"Aadhar: {result['aadhar']}\n"
            text_out += f"Ration Card: {result['ration_card_number']}\n"
            text_out += f"Card Type: {result['card_type']}\n"
            text_out += f"Status: {result['status']}\n"
            text_out += "Family Members:\n"
            for m in result.get("family_members", []):
                text_out += f"  - {m['name']} ({m['relation']}, {m['age']})\n"
            return {"text_output": text_out}
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scraping error: {str(e)}")

@app.get("/scrape/bulk")
def scrape_bulk(
    api_key: str = Depends(verify_api_key),
    aadhars: str = Query(..., description="Comma-separated Aadhar numbers"),
    delay: float = Query(2.0, description="Delay between requests in seconds")
):
    """Scrape multiple Aadhar numbers (rate limited)"""
    aadhar_list = [a.strip() for a in aadhars.split(",") if re.match(r"^\d{12}$", a.strip())]
    
    if not aadhar_list:
        raise HTTPException(status_code=400, detail="No valid Aadhar numbers provided")
    
    if len(aadhar_list) > 50:
        raise HTTPException(status_code=400, detail="Maximum 50 Aadhar numbers per request")
    
    session = get_session()
    results = []
    
    for idx, aadhar in enumerate(aadhar_list):
        try:
            data = scrape_ration_by_aadhar(aadhar, session)
            results.append(data)
        except Exception as e:
            results.append({"aadhar": aadhar, "error": str(e)})
        if idx < len(aadhar_list) - 1:
            time.sleep(delay)
    
    return {
        "total": len(results),
        "successful": sum(1 for r in results if "error" not in r),
        "failed": sum(1 for r in results if "error" in r),
        "results": results
    }

@app.get("/keys/list")
def list_keys(api_key: str = Depends(verify_api_key)):
    """List available API keys (admin only - requires master key)"""
    master_key = os.environ.get("MASTER_API_KEY", "")
    if api_key != master_key:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    return {
        "available_keys": VALID_API_KEYS,
        "total_keys": len(VALID_API_KEYS),
        "developer": "Abhay Singh"
    }

@app.get("/health")
def health(api_key: str = Depends(verify_api_key)):
    return {
        "status": "active",
        "developer": "Abhay Singh",
        "mode": "Stress Test",
        "timestamp": time.time()
    }
