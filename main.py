import paramiko
import time
from config import Config

class MinecraftManager:
    def __init__(self):
        self.config = Config()
        self.ssh = None
    
    def connect(self):
        """Connect to Spare PC"""
        self.ssh = paramiko.SSHClient()
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.ssh.connect(
            self.config.HOST, 
            username=self.config.USERNAME, 
            password=self.config.PASSWORD
        )
        print("✅ Connected to server!")
    
    def disconnect(self):
        """Close SSH connection"""
        if self.ssh:
            self.ssh.close()
    
    def start_server(self):
        """Start Minecraft server in screen"""
        cmd = f"cd {self.config.SERVER_PATH} && screen -dmS minecraft java -Xmx{self.config.RAM} -Xms1G -jar server.jar nogui"
        self.ssh.exec_command(cmd)
        print("🚀 Starting Minecraft server...")
        print("   (Wait ~30 seconds for startup)")
    
    def stop_server(self):
        """Stop Minecraft server"""
        cmd = "screen -S minecraft -X stuff 'stop\\n'"
        self.ssh.exec_command(cmd)
        print("⏹️ Stopping Minecraft server...")
    
    def check_status(self):
        """Check if server is running"""
        stdin, stdout, stderr = self.ssh.exec_command("screen -list | grep minecraft")
        output = stdout.read().decode().strip()
        
        if "minecraft" in output:
            print("✅ Server is RUNNING")
            return True
        else:
            print("❌ Server is STOPPED") 
            return False

def main_menu():
    """Interactive menu"""
    print("\n🎮 Minecraft Server Manager")
    print("=" * 30)
    
    manager = MinecraftManager()
    manager.connect()
    
    while True:
        print("\n📋 Choose an option:")
        print("1. 🚀 Start Server")
        print("2. ⏹️  Stop Server") 
        print("3. 📊 Check Status")
        print("4. 🚪 Exit")
        
        choice = input("\nEnter choice (1-4): ").strip()
        
        if choice == "1":
            manager.start_server()
        elif choice == "2":
            manager.stop_server()
        elif choice == "3":
            manager.check_status()
        elif choice == "4":
            print("👋 Goodbye!")
            break
        else:
            print("❌ Invalid choice!")
    
    manager.disconnect()

if __name__ == "__main__":
    main_menu()