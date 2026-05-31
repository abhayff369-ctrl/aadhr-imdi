# api/index.py - Vercel serverless function with 5 hardcoded keys
from fastapi import FastAPI, Query, HTTPException, Header
from fastapi.responses import JSONResponse
from typing import Dict, Any, List, Optional
import requests
from bs4 import BeautifulSoup
import re
import time
import os
import json

app = FastAPI(title="Aadhar Ration Scraper API", owner="Abhay Singh", version="2.0")

# ========== 5 HARDCODED API KEYS ==========
VALID_API_KEYS = [
    "XERO-DEEPSEEK-KEY-001",
    "ABHAY-SINGH-MASTER-002", 
    "RATION-SCRAPER-003",
    "OSINT-PRO-004",
    "DEV-STRESS-TEST-005"
]

# Optional: master key for admin endpoints
MASTER_API_KEY = "ABHAY-SINGH-ADMIN-MASTER"

def verify_api_key(api_key: str = Header(None, alias="X-API-Key")):
    """Verify API key from header X-API-Key"""
    if api_key is None:
        raise HTTPException(
            status_code=401, 
            detail="Missing X-API-Key header. Please provide one of the 5 valid keys."
        )
    if api_key not in VALID_API_KEYS and api_key != MASTER_API_KEY:
        raise HTTPException(
            status_code=401, 
            detail=f"Invalid API Key. Valid keys: {', '.join(VALID_API_KEYS)}"
        )
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
    Scrape ration card details linked to an Aadhar number from impds.nic.in
    """
    # Try multiple possible endpoints
    endpoints = [
        "https://impds.nic.in/impdsdeduplication/searchRationByAadhar",
        "https://impds.nic.in/impdsdeduplication/getRationDetails",
        "https://impds.nic.in/impdsdeduplication/aadharSearch"
    ]
    
    # Get initial CSRF from home page
    try:
        home_resp = session.get("https://impds.nic.in/impdsdeduplication/search", timeout=15)
        soup = BeautifulSoup(home_resp.text, 'html.parser')
    except Exception as e:
        return {"error": f"Failed to fetch home page: {str(e)}", "aadhar": aadhar_number}
    
    csrf_token = None
    for name in ['csrf_token', '_token', 'csrfmiddlewaretoken', 'authenticity_token', 'csrf']:
        inp = soup.find('input', {'name': name})
        if inp:
            csrf_token = inp.get('value')
            break
    
    # Try each endpoint
    response = None
    for endpoint in endpoints:
        try:
            payload = {
                "aadharNumber": aadhar_number,
                "aadhar": aadhar_number,
                "csrf_token": csrf_token or "",
                "csrfmiddlewaretoken": csrf_token or "",
                "_token": csrf_token or "",
                "action": "search",
                "submit": "Search"
            }
            response = session.post(endpoint, data=payload, timeout=15)
            if response.status_code == 200:
                break
        except:
            continue
    
    if response is None or response.status_code != 200:
        return {
            "error": "All endpoints failed. Site may be down or structure changed.",
            "aadhar": aadhar_number,
            "status_code": response.status_code if response else None
        }
    
    soup = BeautifulSoup(response.text, 'html.parser')
    
    ration_data = {
        "aadhar": aadhar_number,
        "ration_card_number": None,
        "card_type": None,
        "family_members": [],
        "entitlements": {},
        "status": None,
        "raw_text_preview": response.text[:500] if len(response.text) > 500 else response.text,
        "scraped_at": time.time(),
        "developer": "Abhay Singh"
    }
    
    # Try multiple selector patterns
    card_selectors = [".ration-card-number", ".card-number", "#rationCardNo", 
                      ".card_no", ".rationNo", "td:contains('Card No') + td"]
    for selector in card_selectors:
        elem = soup.select_one(selector)
        if elem:
            ration_data["ration_card_number"] = elem.text.strip()
            break
    
    type_selectors = [".card-type", ".type", "#cardType", ".rationType"]
    for selector in type_selectors:
        elem = soup.select_one(selector)
        if elem:
            ration_data["card_type"] = elem.text.strip()
            break
    
    # Family members - look for tables
    tables = soup.find_all("table")
    for table in tables:
        if "member" in str(table).lower() or "family" in str(table).lower():
            rows = table.find_all("tr")
            for row in rows[1:10]:  # Max 9 members
                cols = row.find_all("td")
                if len(cols) >= 2:
                    ration_data["family_members"].append({
                        "name": cols[0].text.strip() if len(cols) > 0 else "",
                        "relation": cols[1].text.strip() if len(cols) > 1 else "",
                        "age": cols[2].text.strip() if len(cols) > 2 else ""
                    })
            break
    
    # Status/error message
    status_selectors = [".status", ".alert", ".error", ".success", ".message"]
    for selector in status_selectors:
        elem = soup.select_one(selector)
        if elem and elem.text.strip():
            ration_data["status"] = elem.text.strip()
            break
    
    return ration_data

# ========== API ENDPOINTS ==========
@app.get("/")
def root():
    return {
        "name": "Aadhar Ration Scraper API",
        "developer": "Abhay Singh",
        "version": "2.0",
        "description": "Search ration card details by Aadhar number",
        "authentication": {
            "header": "X-API-Key",
            "valid_keys": VALID_API_KEYS,
            "total_keys": 5
        },
        "endpoints": [
            {"path": "/", "method": "GET", "description": "API info"},
            {"path": "/scrape/ration?adhar=123456789012", "method": "GET", "description": "Search single Aadhar"},
            {"path": "/scrape/bulk?aadhars=123456789012,234567890123", "method": "GET", "description": "Bulk search (max 50)"},
            {"path": "/keys/list", "method": "GET", "description": "List valid keys (admin)"},
            {"path": "/health", "method": "GET", "description": "Health check"}
        ],
        "example_curl": 'curl -X GET "https://your-vercel-url.vercel.app/scrape/ration?adhar=123456789012" -H "X-API-Key: XERO-DEEPSEEK-KEY-001"'
    }

@app.get("/scrape/ration")
def scrape_ration(
    api_key: str = Header(..., alias="X-API-Key"),
    aadhar: str = Query(..., description="12-digit Aadhar number", min_length=12, max_length=12),
    format: str = Query("json", description="Output format: json or text")
):
    """Scrape ration card details using Aadhar number"""
    
    # Verify key
    if api_key not in VALID_API_KEYS and api_key != MASTER_API_KEY:
        return JSONResponse(
            status_code=401,
            content={
                "error": "Invalid API Key",
                "valid_keys": VALID_API_KEYS,
                "message": "Use one of the 5 keys provided"
            }
        )
    
    # Validate Aadhar
    if not re.match(r"^\d{12}$", aadhar):
        return JSONResponse(
            status_code=400,
            content={"error": "Aadhar must be exactly 12 digits", "provided": aadhar}
        )
    
    try:
        session = get_session()
        result = scrape_ration_by_aadhar(aadhar, session)
        
        if format == "text":
            text_out = f"""
╔══════════════════════════════════════════════════════════════╗
║              RATION CARD SEARCH RESULT                      ║
║                    Developer: Abhay Singh                    ║
╚══════════════════════════════════════════════════════════════╝

📌 AADHAR NUMBER: {result['aadhar']}
📋 RATION CARD NO: {result['ration_card_number'] or 'Not found'}
🏷️  CARD TYPE: {result['card_type'] or 'Not found'}
📊 STATUS: {result['status'] or 'Unknown'}

👨‍👩‍👧‍👦 FAMILY MEMBERS ({len(result.get('family_members', []))}):
"""
            for m in result.get("family_members", []):
                text_out += f"   • {m['name']} - {m['relation']} (Age: {m['age']})\n"
            
            if result.get("entitlements"):
                text_out += "\n🍚 ENTITLEMENTS:\n"
                for k, v in result.get("entitlements", {}).items():
                    text_out += f"   • {k}: {v}\n"
            
            text_out += f"\n⏱️  Scraped at: {time.ctime(result['scraped_at'])}"
            return {"text_output": text_out}
        
        return result
        
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Scraping error: {str(e)}", "aadhar": aadhar}
        )

@app.get("/scrape/bulk")
def scrape_bulk(
    api_key: str = Header(..., alias="X-API-Key"),
    aadhars: str = Query(..., description="Comma-separated Aadhar numbers"),
    delay: float = Query(2.0, description="Delay between requests in seconds")
):
    """Scrape multiple Aadhar numbers (rate limited to 50)"""
    
    # Verify key
    if api_key not in VALID_API_KEYS and api_key != MASTER_API_KEY:
        return JSONResponse(
            status_code=401,
            content={"error": "Invalid API Key", "valid_keys": VALID_API_KEYS}
        )
    
    aadhar_list = [a.strip() for a in aadhars.split(",") if re.match(r"^\d{12}$", a.strip())]
    
    if not aadhar_list:
        return JSONResponse(
            status_code=400,
            content={"error": "No valid Aadhar numbers provided"}
        )
    
    if len(aadhar_list) > 50:
        return JSONResponse(
            status_code=400,
            content={"error": "Maximum 50 Aadhar numbers per request", "provided": len(aadhar_list)}
        )
    
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
        "developer": "Abhay Singh",
        "total": len(results),
        "successful": sum(1 for r in results if "error" not in r),
        "failed": sum(1 for r in results if "error" in r),
        "results": results
    }

@app.get("/keys/list")
def list_keys(api_key: str = Header(..., alias="X-API-Key")):
    """List all 5 valid API keys (requires master key)"""
    if api_key != MASTER_API_KEY:
        return JSONResponse(
            status_code=403,
            content={
                "error": "Admin access required",
                "message": f"Use master key: {MASTER_API_KEY}"
            }
        )
    
    return {
        "developer": "Abhay Singh",
        "total_keys": len(VALID_API_KEYS),
        "keys": VALID_API_KEYS,
        "master_key": MASTER_API_KEY,
        "usage": "Send X-API-Key header with any of these keys"
    }

@app.get("/health")
def health(api_key: str = Header(None, alias="X-API-Key")):
    """Health check - works even without API key"""
    return {
        "status": "active",
        "developer": "Abhay Singh",
        "mode": "Stress Test",
        "timestamp": time.time(),
        "api_keys_configured": len(VALID_API_KEYS)
    }
