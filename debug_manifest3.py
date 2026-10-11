import base64, struct, sys

sys.path.insert(0, ".")
from protect_apk import TEMPL

manifest_b64 = TEMPL["AndroidManifest.xml"]["d"]
data = base64.b64decode(manifest_b64)

# String pool starts at offset 8
sp_off = 8
sp_header_size = struct.unpack_from("<H", data, sp_off + 2)[0]
sp_size = struct.unpack_from("<I", data, sp_off + 4)[0]
sp_string_count = struct.unpack_from("<I", data, sp_off + 8)[0]
sp_flags = struct.unpack_from("<I", data, sp_off + 16)[0]
sp_strings_start = struct.unpack_from("<I", data, sp_off + 20)[0]

is_utf8 = bool(sp_flags & 0x100)
abs_strings_start = sp_off + sp_strings_start
offsets_start = sp_off + 28

def read_string(idx):
    if idx < 0 or idx >= sp_string_count:
        return f"<invalid idx {idx}>"
    off = struct.unpack_from("<I", data, offsets_start + idx * 4)[0]
    p = abs_strings_start + off
    if is_utf8:
        v = data[p]; p += 1 if not (v & 0x80) else 2
        v = data[p]; p += 1 if not (v & 0x80) else 2
        byte_len = data[p - 1] if not (data[p-1] & 0x80) else ((data[p-2] & 0x7F) << 8 | data[p-1])
        # simpler: just read until null
        end = data.index(0, p)
        return data[p:end].decode("utf-8", errors="replace")
    else:
        v = struct.unpack_from("<H", data, p)[0]
        if v & 0x8000:
            char_len = ((v & 0x7FFF) << 16) | struct.unpack_from("<H", data, p + 2)[0]
            p += 4
        else:
            char_len = v; p += 2
        byte_len = char_len * 2
        return data[p:p + byte_len].decode("utf-16-le", errors="replace")

# XML tree starts after string pool
tree_start = sp_off + sp_size
print(f"String pool ends at offset {tree_start}")

# Parse XML tree
# Each chunk: type(2) + headerSize(2) + size(4) + [data...]
pos = tree_start
NS = "http://schemas.android.com/apk/res/android"

element_stack = []
indent = 0

while pos < len(data) - 8:
    chunk_type = struct.unpack_from("<H", data, pos)[0]
    chunk_hsize = struct.unpack_from("<H", data, pos + 2)[0]
    chunk_size = struct.unpack_from("<I", data, pos + 4)[0]
    
    if chunk_size < 8 or pos + chunk_size > len(data):
        break
    
    if chunk_type == 0x0100:  # START_NAMESPACE
        prefix_idx = struct.unpack_from("<I", data, pos + 8)[0]
        uri_idx = struct.unpack_from("<I", data, pos + 12)[0]
        # Don't print namespace decls
        pos += chunk_size
        continue
    
    elif chunk_type == 0x0101:  # END_NAMESPACE
        pos += chunk_size
        continue
    
    elif chunk_type == 0x0102:  # START_ELEMENT
        # Line(4) + comment(4) + ns(4) + name(4) + attrStart(2) + attrSize(2) + attrCount(2) + idIndex(2) + classIndex(2) + styleIndex(2)
        line = struct.unpack_from("<I", data, pos + 8)[0]
        ns_idx = struct.unpack_from("<i", data, pos + 16)[0]
        name_idx = struct.unpack_from("<i", data, pos + 20)[0]
        attr_start = struct.unpack_from("<H", data, pos + 24)[0]
        attr_size = struct.unpack_from("<H", data, pos + 26)[0]
        attr_count = struct.unpack_from("<H", data, pos + 28)[0]
        
        ns_str = read_string(ns_idx) if ns_idx >= 0 else ""
        name_str = read_string(name_idx)
        
        prefix = "  " * indent
        print(f"{prefix}<{name_str}>")
        
        # Parse attributes
        # Each attr: ns(4) + name(4) + rawValue(4) + typedValueSize(2) + typedValueType(2) + typedValueData(4) = 20 bytes
        attr_base = pos + 36  # after the element header
        for ai in range(attr_count):
            a_off = attr_base + ai * 20
            a_ns = struct.unpack_from("<i", data, a_off)[0]
            a_name = struct.unpack_from("<i", data, a_off + 4)[0]
            a_raw = struct.unpack_from("<i", data, a_off + 8)[0]
            a_tsize = struct.unpack_from("<H", data, a_off + 12)[0]
            a_ttype = struct.unpack_from("<H", data, a_off + 14)[0]
            a_tdata = struct.unpack_from("<I", data, a_off + 16)[0]
            
            a_ns_str = read_string(a_ns) if a_ns >= 0 else ""
            a_name_str = read_string(a_name)
            
            if a_ttype == 0x03:  # TYPE_STRING
                a_val = read_string(a_tdata)
            elif a_ttype == 0x10:  # TYPE_INT_DEC
                # Sign extend from 32 bits
                a_val = a_tdata if a_tdata < 0x80000000 else a_tdata - 0x100000000
            elif a_ttype == 0x12:  # TYPE_INT_BOOLEAN
                a_val = "true" if a_tdata != 0 else "false"
            else:
                a_val = f"type=0x{a_ttype:04x} data=0x{a_tdata:08x}"
            
            ns_short = "android:" if "android" in a_ns_str else ""
            print(f"{prefix}  {ns_short}{a_name_str} = {a_val}  [type=0x{a_ttype:04x}]")
        
        indent += 1
        pos += chunk_size
        continue
    
    elif chunk_type == 0x0103:  # END_ELEMENT
        ns_idx = struct.unpack_from("<i", data, pos + 12)[0]
        name_idx = struct.unpack_from("<i", data, pos + 16)[0]
        name_str = read_string(name_idx)
        indent -= 1
        prefix = "  " * indent
        print(f"{prefix}</{name_str}>")
        pos += chunk_size
        continue
    
    else:
        print(f"  Unknown chunk type 0x{chunk_type:04x} at offset {pos}")
        pos += chunk_size
        continue
