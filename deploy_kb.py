#!/usr/bin/env python3
"""deploy_kb.py — Deploy KB bot to VPS as a new instance."""
import os
import sys
import time
import paramiko

HOST = "162.19.81.122"
PORT = 20056
USER = "root"
PASS = "yfoTsKjtY8UgVUsY"

# New bot directory (separate from existing hathixfud-bot)
REMOTE_DIR = "/root/.sop/hathixfud-bot-kb"
LOCAL_DIR = os.path.dirname(os.path.abspath(__file__))

# Files to upload
UPLOAD_FILES = [
    "hathixfud_bot.py",
    "database.py",
    "protect_apk.py",
    "kb_manager.py",
    "kb_analyzer.py",
    ".env",
    "config.json",
    "start.sh",
]

SERVICE_NAME = "hathixfud-bot-kb"


def deploy():
    print(f"[*] Connecting to {USER}@{HOST}:{PORT}...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, port=PORT, username=USER, password=PASS, timeout=15)
    print("[+] Connected!")

    sftp = ssh.open_sftp()

    # Create remote directory
    print(f"[*] Creating remote dir: {REMOTE_DIR}")
    ssh.exec_command(f"mkdir -p {REMOTE_DIR}/keys")
    time.sleep(1)

    # Upload files
    for fname in UPLOAD_FILES:
        local = os.path.join(LOCAL_DIR, fname)
        if not os.path.exists(local):
            print(f"[!] Skipping {fname} (not found locally)")
            continue
        remote = f"{REMOTE_DIR}/{fname}"
        print(f"[*] Uploading {fname}...")
        sftp.put(local, remote)
        print(f"[+] {fname} uploaded")

    # Upload keys directory
    local_keys = os.path.join(LOCAL_DIR, "keys")
    if os.path.isdir(local_keys):
        for kf in os.listdir(local_keys):
            lp = os.path.join(local_keys, kf)
            if os.path.isfile(lp):
                rp = f"{REMOTE_DIR}/keys/{kf}"
                print(f"[*] Uploading keys/{kf}...")
                sftp.put(lp, rp)
                print(f"[+] keys/{kf} uploaded")

    sftp.close()

    # Create systemd service
    print(f"[*] Creating systemd service: {SERVICE_NAME}")
    service_content = f"""[Unit]
Description=HathixFud KB Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory={REMOTE_DIR}
ExecStart=/usr/bin/python3 {REMOTE_DIR}/hathixfud_bot.py
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
"""
    # Write service file
    stdin, stdout, stderr = ssh.exec_command(f"cat > /etc/systemd/system/{SERVICE_NAME}.service << 'EOF'\n{service_content}EOF")
    stdout.channel.recv_exit_status()

    # Reload systemd and enable service
    print("[*] Enabling service...")
    ssh.exec_command("systemctl daemon-reload")
    time.sleep(1)
    ssh.exec_command(f"systemctl enable {SERVICE_NAME}")
    time.sleep(1)

    # Start the service
    print(f"[*] Starting {SERVICE_NAME}...")
    ssh.exec_command(f"systemctl start {SERVICE_NAME}")
    time.sleep(5)

    # Check status
    stdin, stdout, stderr = ssh.exec_command(f"systemctl is-active {SERVICE_NAME}")
    status = stdout.read().decode().strip()
    if status == "active":
        print(f"[+] {SERVICE_NAME} is running!")
    else:
        print(f"[!] Service status: {status}")
        stdin, stdout, stderr = ssh.exec_command(f"journalctl -u {SERVICE_NAME} --no-pager -n 30")
        print(stdout.read().decode())

    ssh.close()
    print("[*] Deploy complete!")
    print(f"[*] Bot directory: {REMOTE_DIR}")
    print(f"[*] Service: {SERVICE_NAME}")


if __name__ == "__main__":
    deploy()
