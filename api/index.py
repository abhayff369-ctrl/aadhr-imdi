# aadhr-imdi/api/index.py
# Developer: Abhay Singh
# API with Query Parameter Authentication: ?key=demo

from fastapi import FastAPI, Query, HTTPException, Request
from fastapi.responses import JSONResponse
from typing import Dict, Any, List, Optional
import requests
from bs4 import BeautifulSoup
import re
import time
import os
import json
import urllib.parse

app = FastAPI(title="Aadhar Ration Scraper API", owner="Abhay Singh", version="3.0")

# ========== API KEYS (Hardcoded) ==========
VALID_API_KEYS = [
    "XERO-DEEPSEEK-KEY-001",
    "ABHAY-SINGH-MASTER-002", 
    "RATION-SCRAPER-003",
    "OSINT-PRO-004",
    "DEV-STRESS-TEST-005"
]

MASTER_API_KEY = "ABHAY-SINGH-ADMIN-MASTER"
DEMO_KEY = "demo"  # Demo key for testing

def verify_api_key(key: Optional[str] = None) -> bool:
    """Verify API key from query parameter 'key'"""
    if key is None:
        return False
    if key in VALID_API_KEYS or key == MASTER_API_KEY or key == DEMO_KEY:
        return True
    return False

# ========== SESSION MANAGEMENT ==========
def get_session():
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,hi;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1"
    })
    return session

# ========== SCRAPING FUNCTION ==========
def scrape_ration_by_aadhar(aadhar_number: str, session: requests.Session) -> Dict[str, Any]:
    """
    Scrape ration card details linked to an Aadhar number from impds.nic.in
    """
    
    # Clean Aadhar - remove any non-digit characters
    aadhar_clean = re.sub(r'\D', '', aadhar_number)
    if len(aadhar_clean) != 12:
        return {"error": f"Invalid Aadhar: {aadhar_number} must be 12 digits", "aadhar": aadhar_number}
    
    # Base URL for the website
    base_url = "https://impds.nic.in/impdsdeduplication"
    
    endpoints = [
        f"{base_url}/searchRationByAadhar",
        f"{base_url}/getRationDetails",
        f"{base_url}/aadharSearch",
        f"{base_url}/search"
    ]
    
    # Get initial page to extract CSRF token
    try:
        home_resp = session.get(f"{base_url}/search", timeout=20)
        home_resp.raise_for_status()
        soup = BeautifulSoup(home_resp.text, 'html.parser')
    except Exception as e:
        return {"error": f"Connection to impds.nic.in failed: {str(e)}", "aadhar": aadhar_clean}
    
    # Extract CSRF token
    csrf_token = None
    csrf_names = ['csrf_token', '_token', 'csrfmiddlewaretoken', 'authenticity_token', 'csrf', 'csrfToken']
    for name in csrf_names:
        inp = soup.find('input', {'name': name})
        if inp:
            csrf_token = inp.get('value')
            break
        inp = soup.find('input', {'id': name})
        if inp:
            csrf_token = inp.get('value')
            break
    
    # Also try to get from meta tag
    if not csrf_token:
        meta = soup.find('meta', {'name': 'csrf-token'})
        if meta:
            csrf_token = meta.get('content')
    
    response = None
    response_text = None
    
    # Try each endpoint
    for endpoint in endpoints:
        try:
            payload = {
                "aadharNumber": aadhar_clean,
                "aadhar": aadhar_clean,
                "aadhar_card_number": aadhar_clean,
                "uid": aadhar_clean,
                "csrf_token": csrf_token or "",
                "csrfmiddlewaretoken": csrf_token or "",
                "_token": csrf_token or "",
                "action": "search",
                "submit": "Search",
                "search": "Search"
            }
            
            response = session.post(endpoint, data=payload, timeout=20)
            
            if response.status_code == 200:
                response_text = response.text
                break
        except:
            continue
    
    if response_text is None:
        return {
            "error": "Unable to fetch data from impds.nic.in. Site may be down or API structure changed.",
            "aadhar": aadhar_clean,
            "tip": "Try using a different Aadhar number or check if the website is accessible"
        }
    
    soup = BeautifulSoup(response_text, 'html.parser')
    
    # Initialize result data
    ration_data = {
        "aadhar": aadhar_clean,
        "ration_card_number": None,
        "card_type": None,
        "family_members": [],
        "entitlements": {},
        "status": None,
        "message": None,
        "scraped_at": time.time(),
        "developer": "Abhay Singh",
        "source": "impds.nic.in"
    }
    
    # Try to find if there's an error message on the page
    error_patterns = ['not found', 'invalid', 'no record', 'does not exist', 'error', 'not registered']
    text_lower = response_text.lower()
    for pattern in error_patterns:
        if pattern in text_lower:
            error_div = soup.find('div', {'class': re.compile(r'error|alert|danger|warning', re.I)})
            if error_div:
                ration_data["message"] = error_div.text.strip()
            else:
                ration_data["message"] = f"No record found for Aadhar: {aadhar_clean}"
            break
    
    # Extract ration card number
    card_selectors = [
        '.ration-card-number', '.card-number', '#rationCardNo', '.rationNo',
        '.card_no', '.rationId', '.ration_id', 'td:contains("Card No") + td',
        'td:contains("Ration Card") + td', 'span.ration-number'
    ]
    for selector in card_selectors:
        try:
            if selector.startswith('td:'):
                # Handle complex selectors differently
                elements = soup.find_all('td')
                for elem in elements:
                    if 'card' in elem.text.lower() or 'ration' in elem.text.lower():
                        next_elem = elem.find_next_sibling('td')
                        if next_elem and next_elem.text.strip():
                            ration_data["ration_card_number"] = next_elem.text.strip()
                            break
            else:
                elem = soup.select_one(selector)
                if elem and elem.text.strip():
                    ration_data["ration_card_number"] = elem.text.strip()
                    break
        except:
            continue
    
    # Extract card type
    type_selectors = ['.card-type', '.type', '#cardType', '.rationType', '.card_category']
    for selector in type_selectors:
        elem = soup.select_one(selector)
        if elem and elem.text.strip():
            ration_data["card_type"] = elem.text.strip()
            break
    
    # Extract family members from tables
    tables = soup.find_all('table')
    for table in tables:
        table_text = str(table).lower()
        if 'member' in table_text or 'family' in table_text or 'name' in table_text:
            rows = table.find_all('tr')
            headers = []
            header_row = rows[0] if rows else None
            if header_row:
                header_cells = header_row.find_all(['th', 'td'])
                headers = [h.text.strip().lower() for h in header_cells]
            
            for row in rows[1:15]:  # Limit to 14 members
                cols = row.find_all('td')
                if len(cols) >= 2:
                    member = {}
                    for i, col in enumerate(cols):
                        col_text = col.text.strip()
                        if i == 0 or (headers and 'name' in headers[i] if i < len(headers) else i == 0):
                            member['name'] = col_text
                        elif i == 1 or (headers and 'relation' in headers[i] if i < len(headers) else i == 1):
                            member['relation'] = col_text
                        elif i == 2 or (headers and 'age' in headers[i] if i < len(headers) else i == 2):
                            member['age'] = col_text
                        elif i == 3:
                            member['gender'] = col_text
                    
                    if member.get('name') or member.get('relation'):
                        if 'name' not in member:
                            member['name'] = cols[0].text.strip() if len(cols) > 0 else ''
                        if 'relation' not in member:
                            member['relation'] = cols[1].text.strip() if len(cols) > 1 else ''
                        if 'age' not in member:
                            member['age'] = cols[2].text.strip() if len(cols) > 2 else ''
                        ration_data["family_members"].append(member)
            
            if ration_data["family_members"]:
                break
    
    # Extract entitlements (food grains)
    entitlement_patterns = ['wheat', 'rice', 'sugar', 'kerosene', 'dal', 'pulses', 'grain', 'entitlement']
    for pattern in entitlement_patterns:
        pattern_match = re.search(rf'{pattern}[:\s]*([0-9.]+)', response_text, re.I)
        if pattern_match:
            ration_data["entitlements"][pattern.title()] = pattern_match.group(1)
    
    # Extract status
    status_selectors = ['.status', '.alert', '.badge', '.card-status', '.active-status']
    for selector in status_selectors:
        elem = soup.select_one(selector)
        if elem and elem.text.strip():
            status_text = elem.text.strip().lower()
            if 'active' in status_text:
                ration_data["status"] = "Active"
            elif 'inactive' in status_text or 'suspended' in status_text:
                ration_data["status"] = "Inactive"
            else:
                ration_data["status"] = elem.text.strip()
            break
    
    return ration_data

# ========== API ENDPOINTS ==========

@app.get("/")
def root():
    """Root endpoint - API information"""
    return {
        "name": "Aadhar Ration Scraper API",
        "developer": "Abhay Singh",
        "version": "3.0",
        "status": "active",
        "authentication": {
            "method": "Query Parameter",
            "parameter": "key",
            "example": "?aadhar=123456789012&key=demo",
            "valid_keys_count": len(VALID_API_KEYS) + 1,
            "valid_keys": VALID_API_KEYS,
            "demo_key": DEMO_KEY
        },
        "endpoints": [
            {
                "path": "/",
                "method": "GET",
                "description": "API information"
            },
            {
                "path": "/scrape/ration",
                "method": "GET",
                "parameters": "?aadhar=12_digits&key=YOUR_KEY",
                "description": "Search ration card by single Aadhar"
            },
            {
                "path": "/scrape/bulk",
                "method": "GET",
                "parameters": "?aadhars=comma,separated,12_digits&key=YOUR_KEY",
                "description": "Search multiple Aadhar numbers (max 50)"
            },
            {
                "path": "/keys/list",
                "method": "GET",
                "parameters": "?key=MASTER_API_KEY",
                "description": "List all valid API keys (admin only)"
            },
            {
                "path": "/health",
                "method": "GET",
                "description": "Health check - no key required"
            }
        ],
        "quick_start": "https://aadhr.vercel.app/scrape/ration?aadhar=123456789012&key=demo"
    }

@app.get("/scrape/ration")
async def scrape_ration_endpoint(
    aadhar: str = Query(..., description="12-digit Aadhar number", min_length=10, max_length=12),
    key: str = Query(..., description="API Key (use 'demo' for testing)"),
    format: str = Query("json", description="Output format: json or text")
):
    """
    Scrape ration card details using Aadhar number.
    Example: /scrape/ration?aadhar=123456789012&key=demo
    """
    
    # Check API key
    if not verify_api_key(key):
        return JSONResponse(
            status_code=401,
            content={
                "error": "Invalid or missing API Key",
                "message": "Please provide a valid API key in the URL using ?key=YOUR_KEY",
                "valid_keys": VALID_API_KEYS,
                "demo_key": DEMO_KEY,
                "example": "/scrape/ration?aadhar=123456789012&key=demo",
                "full_url": "https://aadhr.vercel.app/scrape/ration?aadhar=123456789012&key=demo"
            }
        )
    
    # Clean Aadhar - remove any non-digit characters
    aadhar_clean = re.sub(r'[^0-9]', '', str(aadhar))
    
    if len(aadhar_clean) != 12:
        return JSONResponse(
            status_code=400,
            content={
                "error": "Invalid Aadhar number",
                "received": aadhar,
                "cleaned": aadhar_clean if aadhar_clean else "",
                "message": "Aadhar must be exactly 12 digits",
                "example": "?aadhar=123456789012&key=demo"
            }
        )
    
    try:
        session = get_session()
        result = scrape_ration_by_aadhar(aadhar_clean, session)
        
        if format == "text":
            text_output = f"""
╔══════════════════════════════════════════════════════════════════╗
║                    RATION CARD SEARCH RESULT                     ║
║                      Developer: Abhay Singh                      ║
╚══════════════════════════════════════════════════════════════════╝

📌 AADHAR NUMBER    : {result.get('aadhar', 'N/A')}
📋 RATION CARD NO   : {result.get('ration_card_number', 'Not Found')}
🏷️  CARD TYPE        : {result.get('card_type', 'Not Found')}
📊 STATUS           : {result.get('status', 'Unknown')}
💬 MESSAGE          : {result.get('message', 'N/A')}

👨‍👩‍👧‍👦 FAMILY MEMBERS ({len(result.get('family_members', []))}):
"""
            for m in result.get('family_members', []):
                name = m.get('name', '')
                relation = m.get('relation', '')
                age = m.get('age', '')
                text_output += f"   • {name} - {relation}" + (f" (Age: {age})" if age else "") + "\n"
            
            if result.get('entitlements'):
                text_output += "\n🍚 ENTITLEMENTS:\n"
                for k, v in result.get('entitlements', {}).items():
                    text_output += f"   • {k}: {v} kg\n"
            
            text_output += f"\n⏱️  Scraped at: {time.ctime(result.get('scraped_at', time.time()))}"
            text_output += f"\n🔗 Source: {result.get('source', 'impds.nic.in')}"
            
            return JSONResponse(content={"output": text_output})
        
        return JSONResponse(content=result)
        
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "error": f"Scraping error: {str(e)}",
                "aadhar": aadhar_clean,
                "tip": "Try again later or check if the website is accessible"
            }
        )

@app.get("/scrape/bulk")
def scrape_bulk(
    aadhars: str = Query(..., description="Comma-separated Aadhar numbers"),
    key: str = Query(..., description="API Key"),
    delay: float = Query(2.0, description="Delay between requests in seconds", ge=0.5, le=5.0)
):
    """
    Bulk scrape multiple Aadhar numbers.
    Example: /scrape/bulk?aadhars=123456789012,234567890123&key=demo
    """
    
    if not verify_api_key(key):
        return JSONResponse(
            status_code=401,
            content={
                "error": "Invalid or missing API Key",
                "valid_keys": VALID_API_KEYS,
                "demo_key": DEMO_KEY,
                "example": "/scrape/bulk?aadhars=123456789012,234567890123&key=demo"
            }
        )
    
    # Clean and validate each Aadhar
    aadhar_list = []
    raw_list = aadhars.split(",")
    
    for a in raw_list:
        clean = re.sub(r'\D', '', a.strip())
        if len(clean) == 12:
            aadhar_list.append(clean)
    
    if not aadhar_list:
        return JSONResponse(
            status_code=400,
            content={
                "error": "No valid 12-digit Aadhar numbers found",
                "received": aadhars,
                "example": "?aadhars=123456789012,234567890123&key=demo"
            }
        )
    
    if len(aadhar_list) > 50:
        return JSONResponse(
            status_code=400,
            content={
                "error": "Maximum 50 Aadhar numbers per request",
                "provided": len(aadhar_list)
            }
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
    
    successful = sum(1 for r in results if "error" not in r)
    failed = sum(1 for r in results if "error" in r)
    
    return JSONResponse(content={
        "developer": "Abhay Singh",
        "total": len(results),
        "successful": successful,
        "failed": failed,
        "delay_seconds": delay,
        "results": results
    })

@app.get("/keys/list")
def list_keys(key: str = Query(..., description="Master API Key")):
    """List all valid API keys (requires master key)"""
    if key != MASTER_API_KEY:
        return JSONResponse(
            status_code=403,
            content={
                "error": "Admin access required",
                "message": "Use master key to access this endpoint",
                "master_key": MASTER_API_KEY
            }
        )
    
    return JSONResponse(content={
        "developer": "Abhay Singh",
        "total_keys": len(VALID_API_KEYS),
        "keys": VALID_API_KEYS,
        "demo_key": DEMO_KEY,
        "master_key": MASTER_API_KEY
    })

@app.get("/health")
def health():
    """Health check endpoint - no API key required"""
    return {
        "status": "active",
        "developer": "Abhay Singh",
        "version": "3.0",
        "timestamp": time.time(),
        "api_keys_configured": len(VALID_API_KEYS),
        "demo_key_available": True
    }

# For local testing
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
