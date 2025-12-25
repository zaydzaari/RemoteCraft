import paramiko
import time
from config import Config

class MinecraftService:
    def __init__(self):
        self.config = Config()
        self.ssh = None
    
    def connect(self):
        """Connect to SSH"""
        self.ssh = paramiko.SSHClient()
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.ssh.connect(
            self.config.HOST, 
            username=self.config.USERNAME, 
            password=self.config.PASSWORD
        )
    
    def disconnect(self):
        """Close SSH connection"""
        if self.ssh:
            self.ssh.close()
            self.ssh = None
    
    def execute_command(self, command):
        """Execute SSH command and return output"""
        stdin, stdout, stderr = self.ssh.exec_command(command)
        output = stdout.read().decode().strip()
        error = stderr.read().decode().strip()
        return output, error
    
    # Server Control
    def is_server_running(self):
        """Check if Minecraft server is running"""
        output, error = self.execute_command("screen -list | grep minecraft")
        return "minecraft" in output
    
    def start_server(self):
        """Start Minecraft server in screen"""
        if self.is_server_running():
            return {"status": "already_running", "message": "Server is already running"}
        
        cmd = f"cd {self.config.SERVER_PATH} && screen -dmS minecraft java -Xmx{self.config.RAM} -Xms1G -jar server.jar nogui"
        output, error = self.execute_command(cmd)
        
        if error:
            return {"status": "error", "message": f"Failed to start: {error}"}
        return {"status": "starting", "message": "Server is starting..."}
    
    def stop_server(self):
        """Stop Minecraft server gracefully"""
        if not self.is_server_running():
            return {"status": "not_running", "message": "Server is not running"}
        
        output, error = self.execute_command("screen -S minecraft -X stuff 'stop\\n'")
        return {"status": "stopping", "message": "Stop command sent"}
    
    def kill_server(self):
        """Force kill Minecraft server"""
        output, error = self.execute_command("pkill -f 'java.*server.jar'")
        return {"status": "killed", "message": "Server process killed"}
    
    def restart_server(self):
        """Restart server (stop then start)"""
        stop_result = self.stop_server()
        if stop_result["status"] == "stopping":
            time.sleep(5)  # Wait for graceful shutdown
        start_result = self.start_server()
        return {"status": "restarting", "message": "Server restarted"}
    
    # Server Management
    def create_server(self):
        """Create new Minecraft server"""
        commands = [
            f"mkdir -p {self.config.SERVER_PATH}",
            f"cd {self.config.SERVER_PATH} && wget -O server.jar https://piston-data.mojang.com/v1/objects/45810d238246d90e811d896f87b14695b7fb6839/server.jar",
            f"cd {self.config.SERVER_PATH} && echo 'eula=true' > eula.txt"
        ]
        
        for cmd in commands:
            output, error = self.execute_command(cmd)
            if error and "File exists" not in error:
                return {"status": "error", "message": f"Failed to create server: {error}"}
        
        return {"status": "created", "message": "Server created successfully"}
    
    def delete_server(self):
        """Delete entire server directory"""
        if self.is_server_running():
            self.kill_server()
        
        output, error = self.execute_command(f"rm -rf {self.config.SERVER_PATH}")
        return {"status": "deleted", "message": "Server deleted"}
    
    def get_server_info(self):
        """Get basic server information"""
        commands = {
            "files": f"ls -la {self.config.SERVER_PATH}",
            "size": f"du -sh {self.config.SERVER_PATH}",
            "exists": f"test -d {self.config.SERVER_PATH} && echo 'exists' || echo 'not_found'"
        }
        
        info = {}
        for key, cmd in commands.items():
            output, error = self.execute_command(cmd)
            info[key] = output if output else error
        
        return info
    
    # Console
    def send_command(self, command):
        """Send command to Minecraft console"""
        if not self.is_server_running():
            return {"status": "not_running", "message": "Server is not running"}
        
        output, error = self.execute_command(f"screen -S minecraft -X stuff '{command}\\n'")
        return {"status": "sent", "message": f"Command '{command}' sent to server"}
    
    def get_logs(self, lines=50):
        """Get recent log lines"""
        output, error = self.execute_command(f"tail -{lines} {self.config.SERVER_PATH}/logs/latest.log 2>/dev/null || echo 'No logs found'")
        return {"logs": output.split('\n') if output else []}
    
    # Stats
    def get_system_stats(self):
        """Get system resource usage"""
        commands = {
            "memory": "free -h | grep Mem",
            "disk": f"df -h {self.config.SERVER_PATH} 2>/dev/null || df -h /",
            "cpu": "uptime | awk '{print $10}' | sed 's/,//'"
        }
        
        stats = {}
        for key, cmd in commands.items():
            output, error = self.execute_command(cmd)
            stats[key] = output if output else "N/A"
        
        return stats
    
    def get_server_stats(self):
        """Get Minecraft server specific stats"""
        if not self.is_server_running():
            return {"status": "not_running"}
        
        # Get Java process info
        output, error = self.execute_command("ps aux | grep 'java.*server.jar' | grep -v grep")
        
        stats = {
            "status": "running",
            "process_info": output if output else "Process not found"
        }
        
        return stats