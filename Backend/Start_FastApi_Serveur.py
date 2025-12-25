from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from minecraft_service import MinecraftService
import uvicorn


app = FastAPI(
    title="Minecraft Server Manager API",
    description="Remote Minecraft server control via SSH",
    version="2.0.0"
)


service = MinecraftService()

def execute_with_ssh(func, *args, **kwargs):
    """Execute function with SSH connection handling"""
    try:
        service.connect()
        result = func(*args, **kwargs)
        service.disconnect()
        return {"success": True, "data": result}
    except Exception as e:
        service.disconnect()
        return {"success": False, "error": str(e)}


class CommandRequest(BaseModel):
    command: str

@app.get("/")
async def root():
    return {"message": "Minecraft Server Manager API", "version": "2.0.0"}


@app.get("/api/server/status")
async def get_server_status():
    """Check if Minecraft server is running"""
    def check_status():
        running = service.is_server_running()
        return {
            "running": running,
            "status": "online" if running else "offline"
        }
    return execute_with_ssh(check_status)

@app.post("/api/server/start")
async def start_server():
    """Start Minecraft server"""
    return execute_with_ssh(service.start_server)

@app.post("/api/server/stop") 
async def stop_server():
    """Stop Minecraft server gracefully"""
    return execute_with_ssh(service.stop_server)

@app.post("/api/server/restart")
async def restart_server():
    """Restart Minecraft server"""
    return execute_with_ssh(service.restart_server)

@app.post("/api/server/kill")
async def kill_server():
    """Force kill Minecraft server"""
    return execute_with_ssh(service.kill_server)

@app.post("/api/server/create")
async def create_server():
    """Create new Minecraft server"""
    return execute_with_ssh(service.create_server)

@app.delete("/api/server/delete")
async def delete_server():
    """Delete entire Minecraft server"""
    return execute_with_ssh(service.delete_server)

@app.get("/api/server/info")
async def get_server_info():
    """Get server information"""
    return execute_with_ssh(service.get_server_info)


@app.post("/api/console/command")
async def send_console_command(request: CommandRequest):
    """Send command to Minecraft console"""
    def send_cmd():
        return service.send_command(request.command)
    return execute_with_ssh(send_cmd)

@app.get("/api/console/logs")
async def get_console_logs(lines: int = 50):
    """Get recent console logs"""
    def get_logs():
        return service.get_logs(lines)
    return execute_with_ssh(get_logs)


@app.get("/api/stats/system")
async def get_system_stats():
    """Get system resource statistics"""
    return execute_with_ssh(service.get_system_stats)

@app.get("/api/stats/server")
async def get_server_stats():
    """Get Minecraft server statistics"""
    return execute_with_ssh(service.get_server_stats)


@app.get("/test")
async def serve_test_page():
    """Serve API test page"""
    return FileResponse("backend/test.html")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
