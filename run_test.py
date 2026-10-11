import paramiko, os

HOST = "162.19.81.122"
PORT = 20056
USER = "root"
PASS = "yfoTsKjtY8UgVUsY"

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, port=PORT, username=USER, password=PASS, timeout=15)

sftp = ssh.open_sftp()
local = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_patch.py")
sftp.put(local, "/tmp/test_patch.py")
sftp.close()

stdin, stdout, stderr = ssh.exec_command("cd /root/.sop/hathixfud-bot && python3 /tmp/test_patch.py", timeout=30)
print("STDOUT:", stdout.read().decode())
print("STDERR:", stderr.read().decode())
ssh.close()
