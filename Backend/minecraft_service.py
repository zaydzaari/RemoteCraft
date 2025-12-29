import paramiko
import json
import os
import time
import uuid
import urllib.request
from config import Config

DATA_DIR = "data"
SERVERS_FILE = os.path.join(DATA_DIR, "servers.json")
VERSIONS_CACHE_FILE = os.path.join(DATA_DIR, "versions_cache.json")

# Mojang API URLs
MOJANG_VERSION_MANIFEST = "https://launchermeta.mojang.com/mc/game/version_manifest.json"

class MinecraftService:
    def __init__(self):
        self.config = Config()
        self.ssh = None
        self._init_data_file()
    
    # ════════════════════════════════════════════════════════════════
    # DATA FILE MANAGEMENT
    # ════════════════════════════════════════════════════════════════
    
    def _init_data_file(self):
        """Create data directory and files if not exists"""
        os.makedirs(DATA_DIR, exist_ok=True)
        if not os.path.exists(SERVERS_FILE):
            with open(SERVERS_FILE, 'w') as f:
                json.dump([], f)
    
    def _load_servers(self):
        """Load servers from JSON file"""
        try:
            with open(SERVERS_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return []
    
    def _save_servers(self, servers):
        """Save servers to JSON file"""
        with open(SERVERS_FILE, 'w') as f:
            json.dump(servers, f, indent=2)
    
    def _find_server(self, server_id):
        """Find a server by ID"""
        servers = self._load_servers()
        for server in servers:
            if server['id'] == server_id:
                return server
        return None
    
    def _update_server(self, server_id, updates):
        """Update a server's data"""
        servers = self._load_servers()
        for i, server in enumerate(servers):
            if server['id'] == server_id:
                servers[i].update(updates)
                self._save_servers(servers)
                return servers[i]
        return None
    
    def _remove_server(self, server_id):
        """Remove a server from JSON"""
        servers = self._load_servers()
        servers = [s for s in servers if s['id'] != server_id]
        self._save_servers(servers)
    
    # ════════════════════════════════════════════════════════════════
    # VERSION MANAGEMENT - AUTO FETCH FROM MOJANG
    # ════════════════════════════════════════════════════════════════
    
    def _fetch_url(self, url):
        """Fetch JSON from URL"""
        try:
            with urllib.request.urlopen(url, timeout=10) as response:
                return json.loads(response.read().decode())
        except Exception as e:
            print(f"❌ Failed to fetch {url}: {e}")
            return None
    
    def _get_versions_cache(self):
        """Load cached versions"""
        try:
            if os.path.exists(VERSIONS_CACHE_FILE):
                with open(VERSIONS_CACHE_FILE, 'r') as f:
                    cache = json.load(f)
                    # Cache valid for 1 hour
                    if time.time() - cache.get('timestamp', 0) < 3600:
                        return cache.get('versions', {})
        except:
            pass
        return {}
    
    def _save_versions_cache(self, versions):
        """Save versions to cache"""
        try:
            with open(VERSIONS_CACHE_FILE, 'w') as f:
                json.dump({
                    'timestamp': time.time(),
                    'versions': versions
                }, f, indent=2)
        except Exception as e:
            print(f"⚠️ Failed to save cache: {e}")
    
    def get_available_versions(self, releases_only=True, limit=30):
        """Get list of available Minecraft versions from Mojang"""
        print("📡 Fetching versions from Mojang...")
        
        # Try cache first
        cache = self._get_versions_cache()
        if cache:
            print("📦 Using cached versions")
            versions = list(cache.keys())
            if releases_only:
                # Filter to releases only (versions like 1.x.x)
                versions = [v for v in versions if not ('w' in v or 'pre' in v or 'rc' in v or 'snapshot' in v.lower())]
            return versions[:limit]
        
        # Fetch from Mojang
        manifest = self._fetch_url(MOJANG_VERSION_MANIFEST)
        if not manifest:
            print("❌ Failed to fetch version manifest")
            return self._get_fallback_versions()
        
        versions_data = {}
        versions_list = []
        
        for v in manifest.get('versions', []):
            version_id = v.get('id', '')
            version_type = v.get('type', '')
            version_url = v.get('url', '')
            
            # Only releases if specified
            if releases_only and version_type != 'release':
                continue
            
            versions_data[version_id] = {
                'type': version_type,
                'url': version_url
            }
            versions_list.append(version_id)
            
            if len(versions_list) >= limit:
                break
        
        # Save to cache
        self._save_versions_cache(versions_data)
        
        print(f"✅ Found {len(versions_list)} versions")
        return versions_list
    
    def get_server_download_url(self, version):
        """Get the server.jar download URL for a specific version"""
        print(f"🔍 Getting download URL for {version}...")
        
        # Check cache first
        cache = self._get_versions_cache()
        if version in cache and 'server_url' in cache[version]:
            print(f"📦 Using cached URL for {version}")
            return cache[version]['server_url']
        
        # Get version manifest
        manifest = self._fetch_url(MOJANG_VERSION_MANIFEST)
        if not manifest:
            return self._get_fallback_url(version)
        
        # Find version URL
        version_url = None
        for v in manifest.get('versions', []):
            if v.get('id') == version:
                version_url = v.get('url')
                break
        
        if not version_url:
            print(f"❌ Version {version} not found")
            return self._get_fallback_url(version)
        
        # Fetch version details
        version_data = self._fetch_url(version_url)
        if not version_data:
            return self._get_fallback_url(version)
        
        # Get server download URL
        server_url = version_data.get('downloads', {}).get('server', {}).get('url')
        
        if server_url:
            print(f"✅ Found server URL for {version}")
            # Update cache
            if version in cache:
                cache[version]['server_url'] = server_url
            else:
                cache[version] = {'server_url': server_url}
            self._save_versions_cache(cache)
            return server_url
        
        print(f"❌ No server download for {version}")
        return self._get_fallback_url(version)
    
    def _get_fallback_versions(self):
        """Fallback versions if Mojang API fails"""
        return [
            "1.21.3", "1.21.2", "1.21.1", "1.21",
            "1.20.6", "1.20.4", "1.20.2", "1.20.1", "1.20",
            "1.19.4", "1.19.3", "1.19.2", "1.19.1", "1.19",
            "1.18.2", "1.18.1", "1.18",
            "1.17.1", "1.17",
            "1.16.5", "1.16.4", "1.16.3", "1.16.2", "1.16.1",
            "1.15.2", "1.14.4", "1.13.2", "1.12.2",
            "1.11.2", "1.10.2", "1.9.4", "1.8.9"
        ]
    
    def _get_fallback_url(self, version):
        """Fallback URLs for common versions"""
        fallback_urls = {
            "1.21.3": "https://piston-data.mojang.com/v1/objects/45810d238246d90e811d896f87b14695b7fb6839/server.jar",
            "1.21.2": "https://piston-data.mojang.com/v1/objects/7bf27679d8d45e4669a59c0d6c20a7df2b4e1e9c/server.jar",
            "1.20.1": "https://piston-data.mojang.com/v1/objects/84194a2f286ef7c14ed7ce0090dba59902951553/server.jar",
            "1.19.4": "https://piston-data.mojang.com/v1/objects/8f3112a1049751cc472ec13e397eade5336ca7ae/server.jar",
            "1.18.2": "https://piston-data.mojang.com/v1/objects/c8f83c5655308435b3dcf03c06d9fe8740a77469/server.jar",
            "1.16.5": "https://launcher.mojang.com/v1/objects/1b557e7b033b583cd9f66746b7a9ab1ec1673ced/server.jar",
            "1.12.2": "https://launcher.mojang.com/v1/objects/886945bfb2b978778c3a0288fd7fab09d315b25f/server.jar",
            "1.8.9": "https://launcher.mojang.com/v1/objects/b58b2ceb36e01bcd8dbf49c8fb66c55a9f0676cd/server.jar",
        }
        return fallback_urls.get(version, fallback_urls["1.21.3"])
    
    # ════════════════════════════════════════════════════════════════
    # SSH CONNECTION
    # ════════════════════════════════════════════════════════════════
    
    def connect(self):
        """Connect to SSH"""
        self.ssh = paramiko.SSHClient()
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.ssh.connect(
            self.config.HOST,
            username=self.config.USERNAME,
            password=self.config.PASSWORD,
            timeout=30,
            banner_timeout=30
        )
    
    def disconnect(self):
        """Disconnect SSH"""
        if self.ssh:
            self.ssh.close()
            self.ssh = None
    
    def _run_command(self, command):
        """Execute SSH command and return output"""
        stdin, stdout, stderr = self.ssh.exec_command(command, timeout=60)
        output = stdout.read().decode().strip()
        error = stderr.read().decode().strip()
        return output, error
    
    # ════════════════════════════════════════════════════════════════
    # SERVER OPERATIONS
    # ════════════════════════════════════════════════════════════════
    
    def list_servers(self):
        """List all servers with live status"""
        servers = self._load_servers()
        
        if not servers:
            return []
        
        # Check which screens are running
        try:
            screen_output, _ = self._run_command("screen -list")
        except:
            screen_output = ""
        
        # Update status for each server
        for server in servers:
            screen_name = server.get('screen_name', '')
            is_running = screen_name in screen_output
            server['status'] = 'online' if is_running else 'offline'
            server['players'] = {'current': 0, 'max': 20}
        
        return servers
    
    def create_server(self, name, version, ram, server_type):
        """Create a new Minecraft server with auto-fetched version"""
        
        # Get download URL for this version
        download_url = self.get_server_download_url(version)
        
        print(f"📦 Creating server: {name}")
        print(f"📋 Version: {version} ({server_type})")
        print(f"💾 RAM: {ram}")
        print(f"📥 URL: {download_url}")
        
        # Generate unique ID and safe name
        server_id = str(uuid.uuid4())[:8]
        safe_name = name.lower().replace(" ", "-").replace("_", "-")
        server_path = f"{self.config.SERVER_PATH}/{safe_name}"
        screen_name = f"mc-{safe_name}"
        
        # Server data
        server_data = {
            "id": server_id,
            "name": name,
            "path": server_path,
            "screen_name": screen_name,
            "version": version,
            "ram": ram,
            "type": server_type,
            "port": 25565,
            "status": "offline",
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # Create server on remote machine
        commands = [
            f"mkdir -p {server_path}",
            f"cd {server_path} && wget -q -O server.jar {download_url}",
            f"echo 'eula=true' > {server_path}/eula.txt"
        ]
        
        for cmd in commands:
            output, error = self._run_command(cmd)
            print(f"  → {cmd[:50]}...")
        
        # Save to JSON
        servers = self._load_servers()
        servers.append(server_data)
        self._save_servers(servers)
        
        print(f"✅ Server created: {name}")
        return {"success": True, "server": server_data}
    
    def start_server(self, server_id):
        """Start a Minecraft server"""
        server = self._find_server(server_id)
        if not server:
            return {"error": "Server not found"}
        
        # Check if already running
        screen_output, _ = self._run_command("screen -list")
        if server['screen_name'] in screen_output:
            return {"status": "already_running", "message": "Server is already running"}
        
        # Start server in screen
        cmd = f"cd {server['path']} && screen -dmS {server['screen_name']} java -Xmx{server['ram']} -Xms1G -jar server.jar nogui"
        self._run_command(cmd)
        
        return {"status": "starting", "message": f"Starting {server['name']}..."}
    
    def stop_server(self, server_id):
        """Stop a server gracefully"""
        server = self._find_server(server_id)
        if not server:
            return {"error": "Server not found"}
        
        # Send stop command to screen
        cmd = f"screen -S {server['screen_name']} -X stuff 'stop\\n'"
        self._run_command(cmd)
        
        return {"status": "stopping", "message": f"Stopping {server['name']}..."}
    
    def restart_server(self, server_id):
        """Restart a server"""
        server = self._find_server(server_id)
        if not server:
            return {"error": "Server not found"}
        
        # Stop first
        self.stop_server(server_id)
        
        # Wait and start
        time.sleep(5)
        self.start_server(server_id)
        
        return {"status": "restarting", "message": f"Restarting {server['aname']}..."}
    
    def kill_server(self, server_id):
        """Force kill a server"""
        server = self._find_server(server_id)
        if not server:
            return {"error": "Server not found"}
        
        # Kill screen session
        self._run_command(f"screen -S {server['screen_name']} -X quit")
        self._run_command("screen -wipe")
        
        return {"status": "killed", "message": f"Killed {server['name']}"}
    
    def delete_server(self, server_id):
        """Delete a server completely"""
        server = self._find_server(server_id)
        if not server:
            return {"error": "Server not found"}
        
        # Kill if running
        self._run_command(f"screen -S {server['screen_name']} -X quit")
        
        # Delete files
        self._run_command(f"rm -rf {server['path']}")
        
        # Remove from JSON
        self._remove_server(server_id)
        
        return {"status": "deleted", "message": f"Deleted {server['name']}"}
    
    def send_command(self, server_id, command):
        """Send command to server console"""
        server = self._find_server(server_id)
        if not server:
            return {"error": "Server not found"}
        
        # Check if running
        screen_output, _ = self._run_command("screen -list")
        if server['screen_name'] not in screen_output:
            return {"error": "Server is not running"}
        
        # Send command
        cmd = f"screen -S {server['screen_name']} -X stuff '{command}\\n'"
        self._run_command(cmd)
        
        return {"status": "sent", "command": command}
    
    def get_logs(self, server_id, lines=50):
        """Get server logs"""
        server = self._find_server(server_id)
        if not server:
            return {"error": "Server not found"}
        
        log_path = f"{server['path']}/logs/latest.log"
        output, error = self._run_command(f"tail -{lines} {log_path} 2>/dev/null || echo 'No logs found'")
        
        return {"logs": output.split('\n') if output else []}