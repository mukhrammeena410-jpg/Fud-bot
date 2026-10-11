import subprocess, time, sys, os

workdir = r"C:\Users\Lucky\OneDrive\Desktop\Advance Fud bot\hathixfud"
bot_script = os.path.join(workdir, "hathixfud_bot.py")
stderr_log = os.path.join(workdir, "bot_stderr.log")
stdout_log = os.path.join(workdir, "bot_stdout.log")

with open(stderr_log, "w") as ef, open(stdout_log, "w") as of:
    proc = subprocess.Popen(
        [sys.executable, bot_script],
        cwd=workdir,
        stdout=of,
        stderr=ef,
    )

print(f"Bot PID: {proc.pid}")

# Wait and print logs
for i in range(30):
    time.sleep(1)
    if proc.poll() is not None:
        print(f"Bot exited with code {proc.returncode}")
        break

print("=== STDERR ===")
with open(stderr_log, "r") as f:
    print(f.read())
print("=== STDOUT ===")
with open(stdout_log, "r") as f:
    print(f.read())
