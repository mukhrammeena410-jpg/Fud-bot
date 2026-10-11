#!/usr/bin/env python3
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('162.19.81.122', port=20056, username='root', password='yfoTsKjtY8UgVUsY', timeout=15)

# Write a helper script on VPS
helper = r'''
import base64, struct, sys

# Load wrapper template
sys.path.insert(0, '/root/.sop/hathixfud-bot-kb')
from protect_apk import TEMPL, ORDER, POISON, OLD_PKG

# Check classes.dex
dex = base64.b64decode(TEMPL["classes.dex"]["d"])
print(f"DEX size: {len(dex)}")
print(f"DEX magic: {dex[:8]}")
print(f"DEX magic hex: {dex[:8].hex()}")

# Check if it's a valid DEX
if dex[:4] == b'dex\n':
    print("DEX format: valid (dex\\n)")
    # Parse header
    ver = dex[4:8].decode('ascii', errors='replace')
    print(f"DEX version: {ver}")
    # file_size at offset 32
    file_size = struct.unpack_from('<I', dex, 32)[0]
    print(f"DEX file_size field: {file_size}")
    print(f"DEX actual size: {len(dex)}")
    if file_size != len(dex):
        print("WARNING: DEX file_size mismatch!")
    # header_size at offset 36
    header_size = struct.unpack_from('<I', dex, 36)[0]
    print(f"DEX header_size: {header_size}")
    # endian_tag at offset 40
    endian = struct.unpack_from('<I', dex, 40)[0]
    print(f"DEX endian_tag: 0x{endian:08x} (expected 0x12345678)")
    # Check class definitions
    class_defs_size = struct.unpack_from('<I', dex, 96)[0]
    class_defs_off = struct.unpack_from('<I', dex, 100)[0]
    print(f"DEX class_defs_size: {class_defs_size}")
    print(f"DEX class_defs_off: {class_defs_off}")
    
    # List class names
    string_ids_size = struct.unpack_from('<I', dex, 56)[0]
    string_ids_off = struct.unpack_from('<I', dex, 60)[0]
    type_ids_size = struct.unpack_from('<I', dex, 64)[0]
    type_ids_off = struct.unpack_from('<I', dex, 68)[0]
    
    print(f"\nString IDs: {string_ids_size} at offset {string_ids_off}")
    print(f"Type IDs: {type_ids_size} at offset {type_ids_off}")
    
    # Read class descriptors
    for i in range(min(class_defs_size, 20)):
        off = class_defs_off + i * 32
        class_idx = struct.unpack_from('<I', dex, off)[0]
        # Get type descriptor
        type_off_addr = type_ids_off + class_idx * 4
        desc_off_addr = struct.unpack_from('<I', dex, type_off_addr)[0]
        # string data
        str_data_off_addr = string_ids_off + desc_off_addr * 4
        str_data_off = struct.unpack_from('<I', dex, str_data_off_addr)[0]
        # Read MUTF-8 string
        p = str_data_off
        while dex[p] == 0:
            p += 1
        # Skip ULEB128
        while dex[p] & 0x80:
            p += 1
        p += 1
        end = dex.index(b'\x00', p)
        name = dex[p:end].decode('utf-8', errors='replace')
        print(f"  Class {i}: {name}")
elif dex[:4] == b'dex\x00':
    print("DEX format: valid (dex\\x00)")
else:
    print(f"DEX format: INVALID (first 4 bytes: {dex[:4]})")

# Check AndroidManifest.xml
manifest = base64.b64decode(TEMPL["AndroidManifest.xml"]["d"])
print(f"\nManifest size: {len(manifest)}")
print(f"Manifest magic: {manifest[:4].hex()}")

# Check resources.arsc
arsc = base64.b64decode(TEMPL["resources.arsc"]["d"])
print(f"\nresources.arsc size: {len(arsc)}")
print(f"resources.arsc header: {arsc[:4].hex()}")
'''

sftp = ssh.open_sftp()
with sftp.open('/tmp/helper_check.py', 'w') as f:
    f.write(helper)
sftp.close()

stdin, stdout, stderr = ssh.exec_command('python3 /tmp/helper_check.py 2>&1')
print(stdout.read().decode())
print(stderr.read().decode())

ssh.close()
