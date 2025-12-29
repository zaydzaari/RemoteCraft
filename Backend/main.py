from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from minecraft_service import MinecraftService
import uvicorn

app = FastAPI(title="Minecraft Manager API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

service = MinecraftService()

# ════════════════════════════════════════════════════════════════
# FIXED: Better SSH wrapper with error handling
# ════════════════════════════════════════════════════════════════

def execute_ssh(func, *args, **kwargs):
    """Execute function with SSH connection - with proper error handling"""
    try:
        print(f"🔌 Connecting to SSH...")
        service.connect()
        
        if service.ssh is None:
            print("❌ SSH connection is None!")
            return {"error": "Failed to connect to server"}
        
        print(f"✅ Connected! Running: {func.__name__}")
        result = func(*args, **kwargs)
        
        print(f"📦 Result: {result}")
        service.disconnect()
        
        return result
        
    except Exception as e:
        print(f"❌ SSH Error: {str(e)}")
        service.disconnect()
        return {"error": str(e)}

# ════════════════════════════════════════════════════════════════
# REQUEST MODELS
# ════════════════════════════════════════════════════════════════

class CreateServerRequest(BaseModel):
    name: str
    version: str
    ram: str
    type: str

class CommandRequest(BaseModel):
    command: str

# ════════════════════════════════════════════════════════════════
# ENDPOINTS
# ════════════════════════════════════════════════════════════════

@app.get("/")
def root():
    return {"message": "Minecraft Manager API", "status": "running"}

@app.get("/api/versions")
def get_versions():
    """Get available Minecraft versions - no SSH needed"""
    try:
        versions = service.get_available_versions(releases_only=True, limit=30)
        return {"versions": versions}
    except Exception as e:
        print(f"❌ Version error: {e}")
        return {"versions": service._get_fallback_versions()}

@app.get("/api/servers")
def list_servers():
    """Get all servers with status"""
    return execute_ssh(service.list_servers)

@app.post("/api/server/create")
def create_server(req: CreateServerRequest):
    """Create a new server"""
    print(f"📦 Creating server: {req.name} ({req.version} {req.type} {req.ram})")
    return execute_ssh(service.create_server, req.name, req.version, req.ram, req.type)

@app.post("/api/server/{server_id}/start")
def start_server(server_id: str):
    """Start a server"""
    return execute_ssh(service.start_server, server_id)

@app.post("/api/server/{server_id}/stop")
def stop_server(server_id: str):
    """Stop a server"""
    return execute_ssh(service.stop_server, server_id)

@app.post("/api/server/{server_id}/restart")
def restart_server(server_id: str):
    """Restart a server"""
    return execute_ssh(service.restart_server, server_id)

@app.post("/api/server/{server_id}/kill")
def kill_server(server_id: str):
    """Force kill a server"""
    return execute_ssh(service.kill_server, server_id)

@app.delete("/api/server/{server_id}")
def delete_server(server_id: str):
    """Delete a server"""
    return execute_ssh(service.delete_server, server_id)

@app.post("/api/server/{server_id}/command")
def send_command(server_id: str, req: CommandRequest):
    """Send command to server"""
    return execute_ssh(service.send_command, server_id, req.command)

@app.get("/api/server/{server_id}/logs")
def get_logs(server_id: str, lines: int = 50):
    """Get server logs"""
    return execute_ssh(service.get_logs, server_id, lines)

# ════════════════════════════════════════════════════════════════
# RUN
# ════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)