import base64, struct, sys

sys.path.insert(0, ".")
from protect_apk import TEMPL

manifest_b64 = TEMPL["AndroidManifest.xml"]["d"]
data = base64.b64decode(manifest_b64)

print(f"Manifest size: {len(data)} bytes")

# RES_XML_HEADER: type(2) + headerSize(2) + size(4)
xml_type = struct.unpack_from("<H", data, 0)[0]
xml_hsize = struct.unpack_from("<H", data, 2)[0]
xml_size = struct.unpack_from("<I", data, 4)[0]
print(f"XML header: type=0x{xml_type:04x}, headerSize={xml_hsize}, size={xml_size}")

# String pool starts after XML header at offset 8
sp_off = 8
sp_type = struct.unpack_from("<H", data, sp_off)[0]
sp_header_size = struct.unpack_from("<H", data, sp_off + 2)[0]
sp_size = struct.unpack_from("<I", data, sp_off + 4)[0]
sp_string_count = struct.unpack_from("<I", data, sp_off + 8)[0]
sp_style_count = struct.unpack_from("<I", data, sp_off + 12)[0]
sp_flags = struct.unpack_from("<I", data, sp_off + 16)[0]
sp_strings_start = struct.unpack_from("<I", data, sp_off + 20)[0]
sp_styles_start = struct.unpack_from("<I", data, sp_off + 24)[0]

is_utf8 = bool(sp_flags & 0x100)
print(f"\nString pool at offset {sp_off}:")
print(f"  type=0x{sp_type:04x}, headerSize={sp_header_size}, size={sp_size}")
print(f"  strings={sp_string_count}, styles={sp_style_count}, flags=0x{sp_flags:x}")
print(f"  stringsStart={sp_strings_start}, stylesStart={sp_styles_start}")
print(f"  UTF-8: {is_utf8}")

# Absolute offset of strings data
abs_strings_start = sp_off + sp_strings_start
offsets_start = sp_off + 28  # after header

strings = []
for i in range(min(sp_string_count, 200)):
    off = struct.unpack_from("<I", data, offsets_start + i * 4)[0]
    p = abs_strings_start + off
    
    if is_utf8:
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
    else:
        v = struct.unpack_from("<H", data, p)[0]
        if v & 0x8000:
            char_len = ((v & 0x7FFF) << 16) | struct.unpack_from("<H", data, p + 2)[0]
            p += 4
        else:
            char_len = v; p += 2
        byte_len = char_len * 2
        s = data[p:p + byte_len].decode("utf-16-le", errors="replace")
    
    strings.append(s)
    if i < 100 or ("version" in s.lower()) or ("1.0" in s):
        print(f"  [{i}] '{s}'")

print(f"\nTotal strings: {sp_string_count}")

# Find specific strings
for i, s in enumerate(strings):
    if s in ("1.0", "versionCode", "versionName", "versionCode", OLD_PKG := "wmhfnq.mvicfbs"):
        print(f"\n  KEY STRING [{i}]: '{s}'")
