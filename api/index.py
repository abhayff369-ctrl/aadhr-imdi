# aadhr-imdi/api/index.py
# Developer: Abhay Singh
# VERSION 6.0 - Multiple Tokens Added

from fastapi import FastAPI, Query, Header
from fastapi.responses import JSONResponse
from typing import Dict, Any, Optional, List
import requests
from bs4 import BeautifulSoup
import re
import time
import json
import random
import os

app = FastAPI(title="Aadhar Ration Scraper API", owner="Abhay Singh", version="6.0")

# ========== MULTIPLE TOKENS / API KEYS ==========
# All tokens that users can use
VALID_API_KEYS = [
    # Original 5 keys
    "XERO-DEEPSEEK-KEY-001",
    "ABHAY-SINGH-MASTER-002", 
    "RATION-SCRAPER-003",
    "OSINT-PRO-004",
    "DEV-STRESS-TEST-005",
    
    # Additional tokens (jo aapne diye)
    "DEMO-TOKEN-001",
    "TEST-USER-002",
    "PREMIUM-KEY-003",
    "BASIC-ACCESS-004",
    "VIP-TOKEN-005",
    "FREE-TIER-006",
    "TRIAL-KEY-007",
    "MONTHLY-SUB-008",
    "YEARLY-PLAN-009",
    "LIFETIME-ACCESS-010",
    
    # More tokens for users
    "USER-ABCD-1234",
    "USER-EFGH-5678",
    "USER-IJKL-9012",
    "API-KEY-ABCDEF",
    "SECRET-TOKEN-12345",
    "BEARER-TOKEN-67890",
    "ACCESS-KEY-2024",
    "AUTH-TOKEN-2025",
    "RATION-API-001",
    "SCRAPER-KEY-002",
    
    # Developer specific
    "ABHAY-DEV-KEY",
    "XERO-MASTER-KEY",
    "DEEPSEEK-ADMIN",
    "RATION-PRO-KEY",
    "OSINT-MASTER-TOKEN",
]

# Admin keys
MASTER_API_KEYS = [
    "ABHAY-SINGH-ADMIN-MASTER",
    "XERO-ADMIN-SECRET",
    "DEEPSEEK-ROOT-ACCESS"
]

# Demo/public keys (rate limited)
DEMO_KEYS = [
    "demo",
    "public",
    "guest",
    "test123",
    "freeuser"
]

def verify_api_key(key: Optional[str] = None) -> tuple:
    """
    Verify API key
    Returns (is_valid, key_type, message)
    """
    if not key:
        return (False, None, "No API key provided")
    
    if key in VALID_API_KEYS:
        return (True, "valid", "Access granted")
    
    if key in MASTER_API_KEYS:
        return (True, "master", "Admin access granted")
    
    if key in DEMO_KEYS:
        return (True, "demo", "Demo access granted (rate limited)")
    
    return (False, None, "Invalid API key")

def get_key_info(key: str) -> Dict:
    """Get information about an API key"""
    if key in MASTER_API_KEYS:
        return {"type": "master", "permissions": ["admin", "full", "keys_list"]}
    elif key in VALID_API_KEYS:
        return {"type": "premium", "permissions": ["search", "bulk", "advanced"]}
    elif key in DEMO_KEYS:
        return {"type": "demo", "permissions": ["search", "rate_limited"], "limit": 10}
    else:
        return {"type": "invalid", "permissions": []}

# ========== RATE LIMITING FOR DEMO KEYS ==========
rate_limits = {}

def check_rate_limit(key: str) -> bool:
    """Check if demo key has exceeded rate limit"""
    if key not in DEMO_KEYS:
        return True  # No limit for premium/master keys
    
    now = time.time()
    hour_ago = now - 3600
    
    if key not in rate_limits:
        rate_limits[key] = []
    
    # Clean old requests
    rate_limits[key] = [t for t in rate_limits[key] if t > hour_ago]
    
    # Demo keys: max 10 requests per hour
    if len(rate_limits[key]) >= 10:
        return False
    
    return True

def add_rate_limit(key: str):
    """Add a request to rate limit tracking"""
    if key in DEMO_KEYS:
        if key not in rate_limits:
            rate_limits[key] = []
        rate_limits[key].append(time.time())

# ========== USER AGENT ROTATION ==========
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15",
    "Mozilla/5.0 (Linux; Android 13; SM-G998B) AppleWebKit/537.36 Chrome/119.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; rv:109.0) Gecko/20100101 Firefox/119.0",
    "Mozilla/5.0 (iPad; CPU OS 16_0 like Mac OS X) AppleWebKit/605.1.15",
]

def get_random_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,hi;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }

# ========== SCRAPING FUNCTION ==========
def scrape_ration_by_aadhar(aadhar: str, key_type: str = "valid") -> Dict[str, Any]:
    """Scrape ration card details"""
    
    aadhar_clean = re.sub(r'\D', '', aadhar)
    if len(aadhar_clean) != 12:
        return {
            "success": False,
            "error": "Invalid Aadhar number",
            "aadhar": aadhar,
            "message": "Aadhar must be exactly 12 digits"
        }
    
    # List of URLs to try
    urls_to_try = [
        ("https://impds.nic.in/impdsdeduplication/searchRationByAadhar", "POST"),
        ("https://impds.nic.in/impdsdeduplication/getRationDetails", "POST"),
        ("https://impds.nic.in/impdsdeduplication/aadharSearch", "POST"),
        ("https://impds.nic.in/impdsdeduplication/search", "POST"),
        (f"https://impds.nic.in/impdsdeduplication/searchRationByAadhar?adhar={aadhar_clean}", "GET"),
        (f"https://impds.nic.in/impdsdeduplication/getDetails?uid={aadhar_clean}", "GET"),
    ]
    
    # Parameter combinations
    param_combinations = [
        {"aadharNumber": aadhar_clean},
        {"aadhar": aadhar_clean},
        {"uid": aadhar_clean},
        {"aadhaar": aadhar_clean},
        {"adhar": aadhar_clean},
        {"aadhar_no": aadhar_clean},
        {"number": aadhar_clean},
        {"search": aadhar_clean},
        {"value": aadhar_clean},
        {"aadhar_card": aadhar_clean},
    ]
    
    for url, method in urls_to_try:
        for params in param_combinations:
            try:
                session = requests.Session()
                session.headers.update(get_random_headers())
                
                response = None
                
                if method == "POST":
                    response = session.post(url, data=params, timeout=15, allow_redirects=True)
                else:
                    response = session.get(url, timeout=15, allow_redirects=True)
                
                if response and response.status_code == 200:
                    if is_valid_response(response.text, aadhar_clean):
                        parsed = parse_response(response.text, aadhar_clean)
                        if parsed.get("found", False):
                            parsed["success"] = True
                            parsed["key_type_used"] = key_type
                            return parsed
                            
            except Exception:
                continue
    
    return {
        "success": False,
        "aadhar": aadhar_clean,
        "error": "No data found",
        "message": "Aadhar not registered or website is down",
        "key_type_used": key_type
    }

def is_valid_response(html: str, aadhar: str) -> bool:
    html_lower = html.lower()
    
    error_keywords = ['not found', 'invalid', 'no record', 'error', 'access denied',
                      'login required', 'session expired', 'unauthorized', 'forbidden']
    
    for keyword in error_keywords:
        if keyword in html_lower:
            return False
    
    valid_indicators = ['ration', 'card', 'family', 'member', 'name', 'father', 
                        'mother', 'aadhar', 'uid', 'beneficiary', 'bpl', 'apl']
    
    for indicator in valid_indicators:
        if indicator in html_lower:
            return True
    
    return aadhar in html

def parse_response(html: str, aadhar: str) -> Dict[str, Any]:
    soup = BeautifulSoup(html, 'html.parser')
    
    result = {
        "found": False,
        "aadhar": aadhar,
        "ration_card_number": None,
        "card_type": None,
        "family_members": [],
        "entitlements": {},
        "status": None,
        "scraped_at": time.time(),
        "developer": "Abhay Singh"
    }
    
    # Extract ration card number
    patterns = [
        r'ration[_\s]?card[_\s]?[no#]*[:\s]*([A-Z0-9/]+)',
        r'card[_\s]?no[:\s]*([A-Z0-9/]+)',
        r'ration[_\s]?id[:\s]*([A-Z0-9/]+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, html, re.I)
        if match:
            result["ration_card_number"] = match.group(1).strip()
            result["found"] = True
            break
    
    # Extract family members from tables
    tables = soup.find_all('table')
    for table in tables:
        rows = table.find_all('tr')
        for row in rows:
            cols = row.find_all('td')
            if len(cols) >= 2:
                member = {}
                for i, col in enumerate(cols[:3]):
                    text = col.text.strip()
                    if i == 0:
                        member['name'] = text
                    elif i == 1:
                        member['relation'] = text
                    elif i == 2:
                        member['age'] = text
                
                if member.get('name') and member.get('relation'):
                    result["family_members"].append(member)
                    result["found"] = True
    
    # Extract status
    html_lower = html.lower()
    if 'active' in html_lower:
        result["status"] = "Active"
    elif 'inactive' in html_lower:
        result["status"] = "Inactive"
    elif 'bpl' in html_lower:
        result["status"] = "BPL"
    elif 'apl' in html_lower:
        result["status"] = "APL"
    
    return result

# ========== API ENDPOINTS ==========

@app.get("/")
def root():
    return {
        "name": "Aadhar Ration Scraper API",
        "developer": "Abhay Singh",
        "version": "6.0",
        "status": "Multiple Tokens Added",
        "total_keys": len(VALID_API_KEYS) + len(MASTER_API_KEYS) + len(DEMO_KEYS),
        "authentication": {
            "method": "Query Parameter",
            "parameter": "key",
            "example": "?aadhar=123456789012&key=YOUR_TOKEN",
            "key_types": ["premium (40+ keys)", "master (3 keys)", "demo (5 keys)"]
        },
        "endpoints": {
            "/": "API information",
            "/scrape/ration?aadhar=XXX&key=XXX": "Single Aadhar search",
            "/scrape/bulk?aadhars=X,Y,Z&key=XXX": "Bulk search (max 20)",
            "/keys/list?key=MASTER_KEY": "List all available keys",
            "/keys/info?key=YOUR_KEY": "Get info about your key",
            "/health": "Health check"
        }
    }

@app.get("/scrape/ration")
async def scrape_ration(
    aadhar: str = Query(..., min_length=10, max_length=12, description="12-digit Aadhar number"),
    key: str = Query(..., description="Your API key/token"),
    format: str = Query("json", description="json or text")
):
    """Search ration card by Aadhar number using your token"""
    
    # Verify API key
    is_valid, key_type, message = verify_api_key(key)
    
    if not is_valid:
        return JSONResponse(
            status_code=401,
            content={
                "success": False,
                "error": "Invalid API Key",
                "message": message,
                "available_keys_count": len(VALID_API_KEYS),
                "tip": "Contact Abhay Singh for a valid key"
            }
        )
    
    # Check rate limit for demo keys
    if key_type == "demo" and not check_rate_limit(key):
        return JSONResponse(
            status_code=429,
            content={
                "success": False,
                "error": "Rate limit exceeded",
                "message": "Demo keys limited to 10 requests per hour",
                "key_type": key_type
            }
        )
    
    # Clean Aadhar
    aadhar_clean = re.sub(r'\D', '', aadhar)
    
    if len(aadhar_clean) != 12:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "Invalid Aadhar",
                "received": aadhar,
                "message": "Aadhar must be exactly 12 digits"
            }
        )
    
    # Add to rate limit
    add_rate_limit(key)
    
    try:
        result = scrape_ration_by_aadhar(aadhar_clean, key_type)
        
        if format == "text":
            output = f"""
╔══════════════════════════════════════════════════════════════════╗
║              AADHAR RATION CARD SEARCH RESULT                   ║
║                    Developer: Abhay Singh                       ║
╚══════════════════════════════════════════════════════════════════╝

🔑 KEY TYPE       : {key_type.upper()}
📌 AADHAR NUMBER  : {result.get('aadhar', 'N/A')}
📋 RATION CARD    : {result.get('ration_card_number', 'Not Found')}
🏷️  CARD TYPE      : {result.get('card_type', 'Not Found')}
📊 STATUS         : {result.get('status', 'Unknown')}
✅ FOUND          : {'Yes' if result.get('found') else 'No'}

"""
            if result.get('family_members'):
                output += f"\n👨‍👩‍👧‍👦 FAMILY MEMBERS ({len(result['family_members'])}):\n"
                for m in result['family_members']:
                    output += f"   • {m.get('name', '')} - {m.get('relation', '')}"
                    if m.get('age'):
                        output += f" (Age: {m['age']})"
                    output += "\n"
            
            output += f"\n⏱️  Searched at: {time.ctime(result.get('scraped_at', time.time()))}"
            
            if result.get('error'):
                output += f"\n⚠️  Error: {result['error']}"
            
            return JSONResponse(content={"output": output})
        
        return JSONResponse(content=result)
        
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(e),
                "aadhar": aadhar_clean
            }
        )

@app.get("/scrape/bulk")
async def scrape_bulk(
    aadhars: str = Query(..., description="Comma-separated Aadhar numbers (max 10 for demo)"),
    key: str = Query(..., description="Your API key"),
    delay: float = Query(1.0, description="Delay between requests")
):
    """Bulk search multiple Aadhar numbers"""
    
    is_valid, key_type, message = verify_api_key(key)
    
    if not is_valid:
        return JSONResponse(status_code=401, content={"error": "Invalid API Key"})
    
    if key_type == "demo" and not check_rate_limit(key):
        return JSONResponse(status_code=429, content={"error": "Rate limit exceeded"})
    
    # Parse Aadhar numbers
    aadhar_list = []
    for a in aadhars.split(","):
        clean = re.sub(r'\D', '', a.strip())
        if len(clean) == 12:
            aadhar_list.append(clean)
    
    if not aadhar_list:
        return JSONResponse(status_code=400, content={"error": "No valid Aadhar numbers"})
    
    # Demo keys limited to 5 bulk searches
    if key_type == "demo" and len(aadhar_list) > 5:
        return JSONResponse(status_code=400, content={"error": "Demo keys limited to 5 Aadhar numbers per bulk request"})
    
    if len(aadhar_list) > 20:
        return JSONResponse(status_code=400, content={"error": "Maximum 20 Aadhar numbers"})
    
    add_rate_limit(key)
    
    results = []
    for i, aadhar in enumerate(aadhar_list):
        try:
            result = scrape_ration_by_aadhar(aadhar, key_type)
            results.append(result)
        except Exception as e:
            results.append({"success": False, "aadhar": aadhar, "error": str(e)})
        
        if i < len(aadhar_list) - 1:
            time.sleep(delay)
    
    successful = sum(1 for r in results if r.get("success") or r.get("found"))
    
    return {
        "developer": "Abhay Singh",
        "key_type": key_type,
        "total": len(results),
        "successful": successful,
        "failed": len(results) - successful,
        "results": results
    }

@app.get("/keys/list")
async def list_keys(key: str = Query(..., description="Master API key")):
    """List all available API keys (master keys only)"""
    
    if key not in MASTER_API_KEYS:
        return JSONResponse(
            status_code=403,
            content={
                "error": "Admin access required",
                "message": "Use a master key to access this endpoint",
                "master_keys": MASTER_API_KEYS
            }
        )
    
    return {
        "developer": "Abhay Singh",
        "total_premium_keys": len(VALID_API_KEYS),
        "premium_keys": VALID_API_KEYS,
        "total_master_keys": len(MASTER_API_KEYS),
        "master_keys": MASTER_API_KEYS,
        "demo_keys": DEMO_KEYS,
        "all_keys_count": len(VALID_API_KEYS) + len(MASTER_API_KEYS) + len(DEMO_KEYS)
    }

@app.get("/keys/info")
async def key_info(key: str = Query(..., description="Your API key")):
    """Get information about your API key"""
    
    is_valid, key_type, message = verify_api_key(key)
    
    if not is_valid:
        return JSONResponse(status_code=401, content={"error": "Invalid key", "key": key[:6] + "..."})
    
    info = get_key_info(key)
    
    return {
        "key": key[:6] + "..." + key[-4:] if len(key) > 10 else key,
        "is_valid": is_valid,
        "key_type": key_type,
        "permissions": info.get("permissions", []),
        "rate_limit": info.get("limit", "unlimited"),
        "developer": "Abhay Singh"
    }

@app.get("/keys/add")
async def add_key(
    new_key: str = Query(..., description="New API key to add"),
    master_key: str = Query(..., description="Master API key for authentication")
):
    """Add a new API key (master keys only)"""
    
    if master_key not in MASTER_API_KEYS:
        return JSONResponse(status_code=403, content={"error": "Admin access required"})
    
    if new_key in VALID_API_KEYS:
        return JSONResponse(status_code=400, content={"error": "Key already exists"})
    
    VALID_API_KEYS.append(new_key)
    
    return {
        "success": True,
        "message": f"Key {new_key[:6]}... added successfully",
        "total_keys": len(VALID_API_KEYS),
        "developer": "Abhay Singh"
    }

@app.get("/health")
async def health():
    return {
        "status": "active",
        "developer": "Abhay Singh",
        "version": "6.0",
        "total_keys_configured": len(VALID_API_KEYS) + len(MASTER_API_KEYS) + len(DEMO_KEYS),
        "timestamp": time.time()
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
