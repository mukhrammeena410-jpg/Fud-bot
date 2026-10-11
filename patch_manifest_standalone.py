#!/usr/bin/env python3
"""Standalone manifest patcher - properly handles binary Android XML."""
import struct, base64, sys, os

def utf16_encode(s):
    encoded = s.encode("utf-16-le")
    return struct.pack("<H", len(s)) + encoded + b"\x00\x00"

def patch_manifest(data, new_vc, new_vn):
    data = bytearray(data)
    
    # XML header
    xml_type = struct.unpack_from("<H", data, 0)[0]
    xml_hdr_size = struct.unpack_from("<H", data, 2)[0]
    xml_total = struct.unpack_from("<I", data, 4)[0]
    print(f"XML: type=0x{xml_type:04x} hdr={xml_hdr_size} total={xml_total} actual={len(data)}")
    
    # String pool header
    sp_off = xml_hdr_size  # usually 8
    sp_type = struct.unpack_from("<H", data, sp_off)[0]
    sp_hdr_size = struct.unpack_from("<H", data, sp_off + 2)[0]
    sp_total = struct.unpack_from("<I", data, sp_off + 4)[0]
    sp_count = struct.unpack_from("<I", data, sp_off + 8)[0]
    sp_style_count = struct.unpack_from("<I", data, sp_off + 12)[0]
    sp_flags = struct.unpack_from("<I", data, sp_off + 16)[0]
    sp_strs_start = struct.unpack_from("<I", data, sp_off + 20)[0]
    sp_styles_start = struct.unpack_from("<I", data, sp_off + 24)[0]
    
    is_utf8 = bool(sp_flags & (1 << 8))
    print(f"SP: type=0x{sp_type:04x} hdr={sp_hdr_size} total={sp_total} count={sp_count} utf8={is_utf8}")
    print(f"SP: strs_start={sp_strs_start} styles_start={sp_styles_start}")
    
    if is_utf8:
        print("ERROR: UTF-8 string pool, cannot patch")
        return None
    
    off_arr_off = sp_off + sp_hdr_size
    abs_strs_off = sp_off + sp_strs_start
    
    # Read string offsets
    offsets = []
    for i in range(sp_count):
        offsets.append(struct.unpack_from("<I", data, off_arr_off + i * 4)[0])
    
    # Find end of last string
    last_off = offsets[-1]
    p = abs_strs_off + last_off
    # UTF-16 string: 2 bytes char_len (high bit may indicate 4-byte len), then chars*2, then 0x0000
    v = struct.unpack_from("<H", data, p)[0]
    char_len = v & 0x7FFF
    if v & 0x8000:
        char_len = (char_len << 16) | struct.unpack_from("<H", data, p + 2)[0]
        p += 4
    else:
        p += 2
    p += char_len * 2 + 2  # UTF-16 data + null
    end_of_strs = p
    print(f"End of string data: {end_of_strs} (abs)")
    print(f"String data region: {abs_strs_off} to {end_of_strs} ({end_of_strs - abs_strs_off} bytes)")
    
    # Build new strings
    new_strs = [
        utf16_encode("versionCode"),
        utf16_encode("versionName"),
        utf16_encode(str(new_vn)),
    ]
    new_indices = [sp_count, sp_count + 1, sp_count + 2]
    new_strs_data = b"".join(new_strs)
    
    # New offsets (relative to abs_strs_off)
    new_offs = []
    cursor = 0
    for s in new_strs:
        new_offs.append(end_of_strs - abs_strs_off + cursor)
        cursor += len(s)
    
    new_offs_bytes = b"".join(struct.pack("<I", o) for o in new_offs)
    new_strs_data = b"".join(new_strs)
    raw_insert = len(new_offs_bytes) + len(new_strs_data)
    
    # The string pool total must be 4-byte aligned for XML tree alignment
    new_sp_total_unaligned = sp_total + raw_insert
    sp_pad = (4 - (new_sp_total_unaligned % 4)) % 4
    insert_size = raw_insert + sp_pad
    
    print(f"New strings: {len(new_strs)} entries, raw_insert={raw_insert} sp_pad={sp_pad} insert_size={insert_size}")
    for i, s in enumerate(new_strs):
        print(f"  [{new_indices[i]}] offset={new_offs[i]} data={s[:40]}")
    
    # Rebuild string pool
    new_sp_total = sp_total + raw_insert + sp_pad
    new_sp_count = sp_count + len(new_strs)
    new_strs_start = sp_strs_start + len(new_offs_bytes)
    
    sp_header = bytearray(data[sp_off:sp_off + sp_hdr_size])
    struct.pack_into("<I", sp_header, 4, new_sp_total)
    struct.pack_into("<I", sp_header, 8, new_sp_count)
    struct.pack_into("<I", sp_header, 20, new_strs_start)
    
    old_offsets = bytes(data[off_arr_off:off_arr_off + sp_count * 4])
    old_str_data = bytes(data[abs_strs_off:end_of_strs])
    
    new_sp = bytes(sp_header) + old_offsets + new_offs_bytes + old_str_data + new_strs_data + b"\x00" * sp_pad
    print(f"New string pool: {len(new_sp)} bytes (was {sp_total})")
    
    # Get XML tree (after string pool)
    tree_start = sp_off + sp_total
    tree_data = bytearray(data[tree_start:])
    
    print(f"XML tree: {len(tree_data)} bytes")
    print(f"Tree first 16 bytes: {tree_data[:16].hex()}")
    
    # Find "manifest" string index dynamically
    manifest_idx = -1
    for i in range(sp_count):
        op = abs_strs_off + offsets[i]
        ov = struct.unpack_from("<H", data, op)[0]
        ocl = ov & 0x7FFF
        if ov & 0x8000:
            ocl = (ocl << 16) | struct.unpack_from("<H", data, op + 2)[0]
            op += 4
        else:
            op += 2
        raw = data[op:op + ocl * 2]
        try:
            s = raw.decode("utf-16-le")
            if s == "manifest":
                manifest_idx = i
                break
        except:
            pass
    
    print(f"'manifest' string index: {manifest_idx}")
    if manifest_idx < 0:
        return None
    
    # Find START_ELEMENT in tree
    mpos = None
    pos = 0
    while pos < len(tree_data) - 8:
        ct = struct.unpack_from("<H", tree_data, pos)[0]
        cs = struct.unpack_from("<I", tree_data, pos + 4)[0]
        if cs < 8 or pos + cs > len(tree_data):
            print(f"  Bad chunk at {pos}: type=0x{ct:04x} size={cs}")
            break
        if ct == 0x0102:  # START_ELEMENT
            name_idx = struct.unpack_from("<i", tree_data, pos + 20)[0]
            if name_idx == manifest_idx:
                mpos = pos
                print(f"  Found manifest element at offset {pos}")
                break
        pos += cs
    
    if mpos is None:
        print("ERROR: manifest element not found!")
        return None
    
    # Read manifest element details
    elem_size = struct.unpack_from("<I", tree_data, mpos + 4)[0]
    attr_count = struct.unpack_from("<H", tree_data, mpos + 28)[0]
    print(f"  elem_size={elem_size} attr_count={attr_count}")
    
    # Build attributes
    android_ns = 34
    
    # versionCode: (ns, name, rawValue=-1, size=20, type=0x10(INT_DEC), data=new_vc)
    vc_attr = struct.pack("<IIi", android_ns, new_indices[0], -1)
    vc_attr += struct.pack("<HBB i", 20, 0, 0x10, new_vc)
    
    # versionName: (ns, name, rawValue=str_idx, size=20, type=0x03(STRING), data=str_idx)
    vn_attr = struct.pack("<IIi", android_ns, new_indices[1], new_indices[2])
    vn_attr += struct.pack("<HBB i", 20, 0, 0x03, new_indices[2])
    
    new_attrs = vc_attr + vn_attr
    print(f"  New attributes: {len(new_attrs)} bytes ({len(new_attrs)//20} attrs)")
    
    # Insert point: after existing attributes
    attrs_end = mpos + 36 + attr_count * 20
    
    # Build new tree with inserted attributes
    new_tree = (bytearray(tree_data[:attrs_end]) +
                bytearray(new_attrs) +
                bytearray(tree_data[attrs_end:]))
    
    # Update manifest element
    struct.pack_into("<I", new_tree, mpos + 4, elem_size + len(new_attrs))
    struct.pack_into("<H", new_tree, mpos + 28, attr_count + 2)
    
    # Assemble final result
    before = bytearray(data[:sp_off])
    result = bytearray(before) + bytearray(new_sp) + bytearray(new_tree)
    
    # Update total size in XML header
    struct.pack_into("<I", result, 4, len(result))
    
    print(f"\nResult: {len(result)} bytes (was {len(data)})")
    
    return bytes(result)


if __name__ == "__main__":
    sys.path.insert(0, '/root/.sop/hathixfud-bot-kb')
    from protect_apk import TEMPL
    
    manifest = base64.b64decode(TEMPL["AndroidManifest.xml"]["d"])
    result = patch_manifest(manifest, 100001, "1.0")
    
    if result:
        # Write patched manifest
        with open("/tmp/patched_manifest.bin", "wb") as f:
            f.write(result)
        print(f"\nPatched manifest written to /tmp/patched_manifest.bin")
        
        # Replace in TEMPL and rebuild APK
        # Build the APK with patched manifest
        import zipfile
        sys.path.insert(0, '/root/.sop/hathixfud-bot-kb')
        from protect_apk import ORDER, POISON, patch_name
        
        templ = dict(TEMPL)
        templ["AndroidManifest.xml"]["d"] = base64.b64encode(result).decode()
        
        # Use protect_apk to build
        with open("/tmp/test_input.apk", "rb") as f:
            apk_bytes = f.read()
        
        from protect_apk import pack
        blob = pack(apk_bytes)
        
        tmp = "/tmp/test_patched.apk"
        with zipfile.ZipFile(tmp, "w") as zz:
            for n in ORDER:
                if n == "assets/nvcgehin":
                    zi = zipfile.ZipInfo(n); zi.compress_type = zipfile.ZIP_DEFLATED
                    zz.writestr(zi, blob)
                    continue
                meta = templ[n]
                data = base64.b64decode(meta["d"])
                zi = zipfile.ZipInfo(n)
                zi.compress_type = zipfile.ZIP_DEFLATED if meta["compress"] == 8 else zipfile.ZIP_STORED
                zz.writestr(zi, data)
        
        print(f"Raw APK written to {tmp}")
        
        # Zipalign and sign
        import subprocess
        subprocess.run(["/android-sdk/build-tools/34.0.0/zipalign", "-f", "4", tmp, "/tmp/test_patched.aligned.apk"], check=True)
        subprocess.run([
            "/android-sdk/build-tools/34.0.0/apksigner", "sign",
            "--ks", "/root/.sop/hathixfud-bot/keys/vida-key.jks",
            "--ks-key-alias", "vida",
            "--ks-pass", "pass:vida-key-pass",
            "--key-pass", "pass:vida-key-pass",
            "--v1-signing-enabled", "true",
            "--min-sdk-version", "24",
            "--out", "/tmp/test_patched_final.apk",
            "/tmp/test_patched.aligned.apk"
        ], check=True)
        
        # Verify
        r = subprocess.run(["aapt", "dump", "badging", "/tmp/test_patched_final.apk"], capture_output=True, text=True)
        print("\nAAPT output:")
        for line in r.stdout.splitlines()[:10]:
            print(f"  {line}")
        
        r2 = subprocess.run(["aapt", "dump", "xmltree", "/tmp/test_patched_final.apk", "AndroidManifest.xml"], capture_output=True, text=True)
        print("\nManifest tree:")
        for line in r2.stdout.splitlines()[:5]:
            print(f"  {line}")
        
        r3 = subprocess.run(["apksigner", "verify", "--verbose", "/tmp/test_patched_final.apk"], capture_output=True, text=True)
        print("\nSignature:")
        for line in r3.stdout.splitlines():
            print(f"  {line}")
        
        print("\nDone! APK at /tmp/test_patched_final.apk")
