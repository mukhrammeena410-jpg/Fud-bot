import paramiko
import os
import sys

HOST = "162.19.81.122"
PORT = 20056
USER = "root"
PASS = os.getenv("DEPLOY_PASSWORD")
REMOTE_DIR = "/root/.sop/hathixfud-bot"
LOCAL_DIR = os.path.dirname(os.path.abspath(__file__))

UPLOAD_FILES = [
    "hathixfud_bot.py",
    "database.py",
    "protect_apk.py",
    ".env",
    "config.json",
    "start.sh",
    "deploy.py",
]

def deploy():
    if not PASS:
        raise SystemExit("DEPLOY_PASSWORD is required in the deployment environment.")
    print(f"[*] Connecting to {USER}@{HOST}:{PORT}...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, port=PORT, username=USER, password=PASS, timeout=15)
    print("[+] Connected!")

    sftp = ssh.open_sftp()

    print(f"[*] Ensuring remote dir exists: {REMOTE_DIR}")
    ssh.exec_command(f"mkdir -p {REMOTE_DIR}/keys")

    for fname in UPLOAD_FILES:
        local = os.path.join(LOCAL_DIR, fname)
        if not os.path.exists(local):
            print(f"[!] Skipping {fname} (not found locally)")
            continue
        remote = f"{REMOTE_DIR}/{fname}"
        print(f"[*] Uploading {fname}...")
        sftp.put(local, remote)
        print(f"[+] {fname} uploaded")

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
    print("[*] Restarting bot via systemd...")
    ssh.exec_command("systemctl restart hathixfud-bot")
    import time; time.sleep(5)

    stdin, stdout, stderr = ssh.exec_command("systemctl is-active hathixfud-bot")
    status = stdout.read().decode().strip()
    if status == "active":
        print("[+] Bot is running!")
    else:
        print(f"[!] Service status: {status}")
        stdin, stdout, stderr = ssh.exec_command("journalctl -u hathixfud-bot --no-pager -n 30")
        print(stdout.read().decode())

    ssh.close()
    print("[*] Deploy complete!")

if __name__ == "__main__":
    deploy()
