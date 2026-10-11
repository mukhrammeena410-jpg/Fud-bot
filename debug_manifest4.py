import base64, struct, sys

sys.path.insert(0, ".")
from protect_apk import TEMPL

manifest_b64 = TEMPL["AndroidManifest.xml"]["d"]
data = bytearray(base64.b64decode(manifest_b64))

# String pool at offset 8
sp_off = 8
sp_flags = struct.unpack_from("<I", data, sp_off + 16)[0]
sp_strings_start = struct.unpack_from("<I", data, sp_off + 20)[0]
sp_string_count = struct.unpack_from("<I", data, sp_off + 8)[0]
sp_size = struct.unpack_from("<I", data, sp_off + 4)[0]
abs_strings_start = sp_off + sp_strings_start
offsets_start = sp_off + 28

def read_string_idx(idx):
    off = struct.unpack_from("<I", data, offsets_start + idx * 4)[0]
    p = abs_strings_start + off
    # UTF-16
    v = struct.unpack_from("<H", data, p)[0]
    if v & 0x8000:
        char_len = ((v & 0x7FFF) << 16) | struct.unpack_from("<H", data, p + 2)[0]
        p += 4
    else:
        char_len = v; p += 2
    byte_len = char_len * 2
    return data[p:p + byte_len]

# Find manifest element
tree_start = sp_off + sp_size
pos = tree_start
while pos < len(data) - 8:
    chunk_type = struct.unpack_from("<H", data, pos)[0]
    chunk_size = struct.unpack_from("<I", data, pos + 4)[0]
    if chunk_size < 8 or pos + chunk_size > len(data):
        break
    if chunk_type == 0x0102:  # START_ELEMENT
        name_idx = struct.unpack_from("<i", data, pos + 20)[0]
        attr_count = struct.unpack_from("<H", data, pos + 28)[0]
        name = read_string_idx(name_idx).decode("utf-16-le", errors="replace")
        if name == "manifest":
            print(f"Found <manifest> at offset {pos}, attrCount={attr_count}")
            print(f"  Element header size: {struct.unpack_from('<H', data, pos+2)[0]}")
            break
    pos += chunk_size

print(f"\nString pool: {sp_string_count} strings, size={sp_size}")
print(f"We need to add: 'versionCode', 'versionName', and version value strings")
print(f"Current manifest element has {attr_count} attribute(s)")

# Check what the current attributes look like
attr_base = pos + 36
for ai in range(attr_count):
    a_off = attr_base + ai * 20
    a_ns = struct.unpack_from("<i", data, a_off)[0]
    a_name = struct.unpack_from("<i", data, a_off + 4)[0]
    a_raw = struct.unpack_from("<i", data, a_off + 8)[0]
    a_ttype = struct.unpack_from("<H", data, a_off + 14)[0]
    a_tdata = struct.unpack_from("<I", data, a_off + 16)[0]
    print(f"  attr[{ai}]: ns={a_ns}, name={a_name}, raw={a_raw}, type=0x{a_ttype:04x}, data=0x{a_tdata:08x}")
