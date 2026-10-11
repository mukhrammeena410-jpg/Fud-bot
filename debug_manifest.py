import base64, struct, sys

# Extract the TEMPL AndroidManifest.xml from protect_apk.py
sys.path.insert(0, ".")
from protect_apk import TEMPL

manifest_b64 = TEMPL["AndroidManifest.xml"]["d"]
data = base64.b64decode(manifest_b64)

print(f"Manifest size: {len(data)} bytes")
print(f"First 4 bytes (magic): {data[:4].hex()}")

# Parse string pool header
# type(2) + headerSize(2) + size(4) + stringCount(4) + styleCount(4) + flags(4) + stringsStart(4) + stylesStart(4)
sp_type = struct.unpack_from("<H", data, 0)[0]
sp_header_size = struct.unpack_from("<H", data, 2)[0]
sp_size = struct.unpack_from("<I", data, 4)[0]
sp_string_count = struct.unpack_from("<I", data, 8)[0]
sp_style_count = struct.unpack_from("<I", data, 12)[0]
sp_flags = struct.unpack_from("<I", data, 16)[0]
sp_strings_start = struct.unpack_from("<I", data, 20)[0]
sp_styles_start = struct.unpack_from("<I", data, 24)[0]

is_utf8 = bool(sp_flags & 0x100)
print(f"\nString pool: type={sp_type}, headerSize={sp_header_size}, size={sp_size}")
print(f"  strings={sp_string_count}, styles={sp_style_count}, flags=0x{sp_flags:x}")
print(f"  stringsStart={sp_strings_start}, stylesStart={sp_styles_start}")
print(f"  UTF-8: {is_utf8}")

# Read string offsets
offsets_start = 28
strings_data_start = sp_strings_start

print(f"\nAll {sp_string_count} strings in pool:")
for i in range(sp_string_count):
    off = struct.unpack_from("<I", data, offsets_start + i * 4)[0]
    p = strings_data_start + off
    
    if is_utf8:
        # UTF-8: char_len (1-2 bytes) + byte_len (1-2 bytes) + bytes + null
        v = data[p]
        if v & 0x80:
            char_len = ((v & 0x7F) << 8) | data[p + 1]; p += 2
        else:
            char_len = v; p += 1
        v = data[p]
        if v & 0x80:
            byte_len = ((v & 0x7F) << 8) | data[p + 1]; p += 2
        else:
            byte_len = v; p += 1
        s = data[p:p + byte_len].decode("utf-8", errors="replace")
        total = p + byte_len + 1 - strings_data_start - off
        print(f"  [{i}] offset={off} char_len={char_len} byte_len={byte_len} total_bytes={total} => '{s}'")
    else:
        v = struct.unpack_from("<H", data, p)[0]
        if v & 0x8000:
            char_len = ((v & 0x7FFF) << 16) | struct.unpack_from("<H", data, p + 2)[0]
            p += 4
        else:
            char_len = v; p += 2
        byte_len = char_len * 2
        s = data[p:p + byte_len].decode("utf-16-le", errors="replace")
        total = p + byte_len + 2 - strings_data_start - off
        print(f"  [{i}] offset={off} char_len={char_len} total_bytes={total} => '{s}'")

# Search for versionCode and versionName in the raw bytes
print(f"\nSearching for version patterns:")
print(f"  '1.0' hex: {b'1.0'.hex()}")
print(f"  Searching...")
idx = 0
while True:
    idx = data.find(b"1.0", idx)
    if idx < 0: break
    context = data[max(0,idx-8):idx+8]
    print(f"  Found '1.0' at offset {idx}, context: {context.hex()}")
    idx += 1

# Search for versionCode string
idx = 0
while True:
    idx = data.find(b"versionCode", idx)
    if idx < 0: break
    print(f"  Found 'versionCode' at offset {idx}")
    idx += 1

# Search for versionName string
idx = 0
while True:
    idx = data.find(b"versionName", idx)
    if idx < 0: break
    print(f"  Found 'versionName' at offset {idx}")
    idx += 1
