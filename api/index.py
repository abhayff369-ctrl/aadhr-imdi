# api/index.py - Fixed version with better error handling
from fastapi import FastAPI, Query, HTTPException, Header, Request
from fastapi.responses import JSONResponse
from typing import Dict, Any, List, Optional
import requests
from bs4 import BeautifulSoup
import re
import time
import os
import json

app = FastAPI(title="Aadhar Ration Scraper API", owner="Abhay Singh", version="2.1")

# ========== 5 HARDCODED API KEYS ==========
VALID_API_KEYS = [
    "XERO-DEEPSEEK-KEY-001",
    "ABHAY-SINGH-MASTER-002", 
    "RATION-SCRAPER-003",
    "OSINT-PRO-004",
    "DEV-STRESS-TEST-005"
]

MASTER_API_KEY = "ABHAY-SINGH-ADMIN-MASTER"

def verify_api_key(api_key: Optional[str] = Header(None, alias="X-API-Key")):
    """Verify API key with friendly error"""
    if api_key is None:
        return None
    if api_key not in VALID_API_KEYS and api_key != MASTER_API_KEY:
        return None
    return api_key

# ========== SESSION MANAGEMENT ==========
def get_session():
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
    })
    return session

# ========== SCRAPING FUNCTION ==========
def scrape_ration_by_aadhar(aadhar_number: str, session: requests.Session) -> Dict[str, Any]:
    """Scrape ration card details linked to an Aadhar number"""
    
    # Clean Aadhar - remove any non-digit characters
    aadhar_clean = re.sub(r'\D', '', aadhar_number)
    if len(aadhar_clean) != 12:
        return {"error": f"Invalid Aadhar: {aadhar_number} must be 12 digits", "aadhar": aadhar_number}
    
    endpoints = [
        "https://impds.nic.in/impdsdeduplication/searchRationByAadhar",
        "https://impds.nic.in/impdsdeduplication/getRationDetails",
    ]
    
    try:
        home_resp = session.get("https://impds.nic.in/impdsdeduplication/search", timeout=15)
        soup = BeautifulSoup(home_resp.text, 'html.parser')
    except Exception as e:
        return {"error": f"Connection failed: {str(e)}", "aadhar": aadhar_clean}
    
    csrf_token = None
    for name in ['csrf_token', '_token', 'csrfmiddlewaretoken']:
        inp = soup.find('input', {'name': name})
        if inp:
            csrf_token = inp.get('value')
            break
    
    response = None
    for endpoint in endpoints:
        try:
            payload = {
                "aadharNumber": aadhar_clean,
                "aadhar": aadhar_clean,
                "csrf_token": csrf_token or "",
                "action": "search",
            }
            response = session.post(endpoint, data=payload, timeout=15)
            if response.status_code == 200:
                break
        except:
            continue
    
    if response is None or response.status_code != 200:
        return {
            "error": "Unable to fetch data. Site may be unavailable.",
            "aadhar": aadhar_clean,
            "status_code": response.status_code if response else None
        }
    
    soup = BeautifulSoup(response.text, 'html.parser')
    
    ration_data = {
        "aadhar": aadhar_clean,
        "ration_card_number": None,
        "card_type": None,
        "family_members": [],
        "status": None,
        "scraped_at": time.time(),
        "developer": "Abhay Singh"
    }
    
    # Extract data with common selectors
    card_selectors = [".ration-card-number", ".card-number", "#rationCardNo", ".rationNo"]
    for selector in card_selectors:
        elem = soup.select_one(selector)
        if elem:
            ration_data["ration_card_number"] = elem.text.strip()
            break
    
    type_selectors = [".card-type", ".type", "#cardType"]
    for selector in type_selectors:
        elem = soup.select_one(selector)
        if elem:
            ration_data["card_type"] = elem.text.strip()
            break
    
    # Look for tables with family members
    tables = soup.find_all("table")
    for table in tables:
        if "member" in str(table).lower() or "family" in str(table).lower():
            rows = table.find_all("tr")
            for row in rows[1:11]:
                cols = row.find_all("td")
                if len(cols) >= 2:
                    ration_data["family_members"].append({
                        "name": cols[0].text.strip() if len(cols) > 0 else "",
                        "relation": cols[1].text.strip() if len(cols) > 1 else "",
                        "age": cols[2].text.strip() if len(cols) > 2 else ""
                    })
            break
    
    status_selectors = [".status", ".alert", ".error", ".success"]
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
        "version": "2.1",
        "authentication": {
            "method": "Header: X-API-Key",
            "valid_keys": VALID_API_KEYS,
            "total_keys": 5
        },
        "correct_usage": {
            "curl_example": 'curl -X GET "https://your-api.vercel.app/scrape/ration?aadhar=123456789012" -H "X-API-Key: XERO-DEEPSEEK-KEY-001"',
            "note": "Do NOT put the -H header inside quotes with the URL. Header is separate."
        },
        "endpoints": [
            {"path": "/", "method": "GET", "description": "This info"},
            {"path": "/scrape/ration?aadhar=123456789012", "method": "GET", "description": "Search single Aadhar"},
            {"path": "/scrape/bulk?aadhars=123456789012,234567890123", "method": "GET", "description": "Bulk search"},
            {"path": "/keys/list", "method": "GET", "description": "List keys (admin only)"},
            {"path": "/health", "method": "GET", "description": "Health check"}
        ]
    }

@app.get("/scrape/ration")
async def scrape_ration_endpoint(
    request: Request,
    aadhar: str = Query(..., description="12-digit Aadhar number"),
    format: str = Query("json", description="json or text"),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
):
    """Scrape ration card details using Aadhar number"""
    
    # Check API key
    if x_api_key is None:
        return JSONResponse(
            status_code=401,
            content={
                "error": "Missing API Key",
                "message": "You must provide X-API-Key header",
                "valid_keys": VALID_API_KEYS,
                "correct_format": 'curl -X GET "URL?adhar=123456789012" -H "X-API-Key: YOUR_KEY"'
            }
        )
    
    if x_api_key not in VALID_API_KEYS and x_api_key != MASTER_API_KEY:
        return JSONResponse(
            status_code=401,
            content={
                "error": "Invalid API Key",
                "provided_key": x_api_key[:10] + "..." if len(x_api_key) > 10 else x_api_key,
                "valid_keys": VALID_API_KEYS
            }
        )
    
    # Clean Aadhar - remove any spaces, quotes, or extra characters
    aadhar_clean = re.sub(r'[^0-9]', '', str(aadhar))
    
    if len(aadhar_clean) != 12:
        return JSONResponse(
            status_code=400,
            content={
                "error": "Invalid Aadhar number",
                "received": aadhar,
                "cleaned": aadhar_clean,
                "message": "Aadhar must be exactly 12 digits. Example: aadhar=123456789012"
            }
        )
    
    try:
        session = get_session()
        result = scrape_ration_by_aadhar(aadhar_clean, session)
        
        if format == "text":
            text_out = f"""
╔════════════════════════════════════════════════════════╗
║           RATION CARD SEARCH RESULT                    ║
║              Developer: Abhay Singh                    ║
╚════════════════════════════════════════════════════════╝

AADHAR: {result['aadhar']}
RATION CARD: {result['ration_card_number'] or 'Not found'}
CARD TYPE: {result['card_type'] or 'Not found'}
STATUS: {result['status'] or 'Unknown'}

FAMILY MEMBERS ({len(result.get('family_members', []))}):
"""
            for m in result.get("family_members", []):
                text_out += f"  • {m['name']} - {m['relation']}\n"
            
            text_out += f"\nScraped: {time.ctime(result['scraped_at'])}"
            return {"output": text_out}
        
        return result
        
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": str(e), "aadhar": aadhar_clean}
        )

@app.get("/scrape/bulk")
def scrape_bulk(
    aadhars: str = Query(..., description="Comma-separated Aadhar numbers"),
    delay: float = Query(2.0, description="Delay between requests"),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
):
    """Bulk scrape multiple Aadhar numbers"""
    
    if x_api_key is None or (x_api_key not in VALID_API_KEYS and x_api_key != MASTER_API_KEY):
        return JSONResponse(
            status_code=401,
            content={"error": "Invalid or missing API Key", "valid_keys": VALID_API_KEYS}
        )
    
    # Clean and validate each Aadhar
    aadhar_list = []
    for a in aadhars.split(","):
        clean = re.sub(r'\D', '', a.strip())
        if len(clean) == 12:
            aadhar_list.append(clean)
    
    if not aadhar_list:
        return JSONResponse(
            status_code=400,
            content={"error": "No valid 12-digit Aadhar numbers found", "received": aadhars}
        )
    
    if len(aadhar_list) > 50:
        return JSONResponse(
            status_code=400,
            content={"error": "Maximum 50 Aadhar numbers", "provided": len(aadhar_list)}
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
def list_keys(x_api_key: Optional[str] = Header(None, alias="X-API-Key")):
    """List all valid API keys (requires master key)"""
    if x_api_key != MASTER_API_KEY:
        return JSONResponse(
            status_code=403,
            content={"error": "Admin access required", "master_key": MASTER_API_KEY}
        )
    
    return {
        "developer": "Abhay Singh",
        "total_keys": len(VALID_API_KEYS),
        "keys": VALID_API_KEYS,
        "master_key": MASTER_API_KEY
    }

@app.get("/health")
def health():
    return {
        "status": "active",
        "developer": "Abhay Singh",
        "timestamp": time.time(),
        "api_keys_configured": len(VALID_API_KEYS)
    }
