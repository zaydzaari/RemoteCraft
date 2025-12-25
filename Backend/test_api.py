import requests
import json
import time

# API base URL
BASE_URL = "http://localhost:8000"

def print_response(endpoint, response):
    """Pretty print API response"""
    print(f"\n🔗 {endpoint}")
    print(f"Status: {response.status_code}")
    try:
        data = response.json()
        print(f"Response: {json.dumps(data, indent=2)}")
    except:
        print(f"Raw Response: {response.text}")
    print("-" * 50)

def test_all_endpoints():
    """Test all API endpoints"""
    
    print("🎮 Testing Minecraft Server API")
    print("=" * 50)
    
    # 1. Test root endpoint
    response = requests.get(f"{BASE_URL}/")
    print_response("GET /", response)
    
    # 2. Check server status
    response = requests.get(f"{BASE_URL}/api/server/status")
    print_response("GET /api/server/status", response)
    
    # 3. Get server info
    response = requests.get(f"{BASE_URL}/api/server/info")
    print_response("GET /api/server/info", response)
    
    # 4. Get system stats
    response = requests.get(f"{BASE_URL}/api/stats/system")
    print_response("GET /api/stats/system", response)
    
    # 5. Create server (if doesn't exist)
    response = requests.post(f"{BASE_URL}/api/server/create")
    print_response("POST /api/server/create", response)
    
    # 6. Start server
    response = requests.post(f"{BASE_URL}/api/server/start")
    print_response("POST /api/server/start", response)
    
    # Wait a bit
    print("⏳ Waiting 5 seconds...")
    time.sleep(5)
    
    # 7. Check status again
    response = requests.get(f"{BASE_URL}/api/server/status")
    print_response("GET /api/server/status (after start)", response)
    
    # 8. Get server stats
    response = requests.get(f"{BASE_URL}/api/stats/server")
    print_response("GET /api/stats/server", response)
    
    # 9. Send command
    response = requests.post(f"{BASE_URL}/api/console/command", 
                           json={"command": "say Hello from API!"})
    print_response("POST /api/console/command", response)
    
    # 10. Get logs
    response = requests.get(f"{BASE_URL}/api/console/logs?lines=10")
    print_response("GET /api/console/logs", response)
    
    # 11. Stop server
    response = requests.post(f"{BASE_URL}/api/server/stop")
    print_response("POST /api/server/stop", response)
    
    print("\n✅ All tests completed!")

def test_individual(endpoint, method="GET", data=None):
    """Test individual endpoint"""
    if method == "GET":
        response = requests.get(f"{BASE_URL}{endpoint}")
    elif method == "POST":
        response = requests.post(f"{BASE_URL}{endpoint}", json=data)
    elif method == "DELETE":
        response = requests.delete(f"{BASE_URL}{endpoint}")
    
    print_response(f"{method} {endpoint}", response)

if __name__ == "__main__":
    print("Choose test mode:")
    print("1. Test all endpoints")
    print("2. Test individual endpoint")
    
    choice = input("Choice (1/2): ")
    
    if choice == "1":
        test_all_endpoints()
    elif choice == "2":
        endpoint = input("Endpoint (e.g., /api/server/status): ")
        method = input("Method (GET/POST/DELETE): ").upper()
        
        data = None
        if method == "POST" and "/command" in endpoint:
            command = input("Command to send: ")
            data = {"command": command}
        
        test_individual(endpoint, method, data)