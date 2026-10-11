import sys, base64, struct
sys.path.insert(0, '/root/.sop/hathixfud-bot')
from protect_apk import TEMPL, patch_manifest_version

data = base64.b64decode(TEMPL['AndroidManifest.xml']['d'])
print('Original size:', len(data))

patched = patch_manifest_version(data, 100001, '2.0')
print('Patched size:', len(patched))

# Verify by parsing string pool
sp_off = 8
sp_string_count = struct.unpack_from('<I', patched, sp_off + 8)[0]
offsets_start = sp_off + 28
abs_strings_start = sp_off + struct.unpack_from('<I', patched, sp_off + 20)[0]
for i in range(sp_string_count):
    off = struct.unpack_from('<I', patched, offsets_start + i * 4)[0]
    p = abs_strings_start + off
    v = struct.unpack_from('<H', patched, p)[0]
    if v & 0x8000:
        cl = ((v & 0x7FFF) << 16) | struct.unpack_from('<H', patched, p + 2)[0]
        p += 4
    else:
        cl = v; p += 2
    s = patched[p:p + cl*2].decode('utf-16-le', errors='replace')
    if 'version' in s.lower() or s in ('2.0',):
        print(f'  String [{i}]: {s}')

# Verify manifest element
tree_start = sp_off + struct.unpack_from('<I', patched, sp_off + 4)[0]
pos = tree_start
while pos < len(patched) - 8:
    ct = struct.unpack_from('<H', patched, pos)[0]
    cs = struct.unpack_from('<I', patched, pos + 4)[0]
    if cs < 8 or pos + cs > len(patched):
        break
    if ct == 0x0102:
        ac = struct.unpack_from('<H', patched, pos + 28)[0]
        name_idx = struct.unpack_from('<i', patched, pos + 20)[0]
        s_off = struct.unpack_from('<I', patched, offsets_start + name_idx * 4)[0]
        sp = abs_strings_start + s_off
        v2 = struct.unpack_from('<H', patched, sp)[0]
        if v2 & 0x8000:
            cl2 = ((v2 & 0x7FFF) << 16) | struct.unpack_from('<H', patched, sp + 2)[0]
            sp2 = sp + 4
        else:
            cl2 = v2; sp2 = sp + 2
        ename = patched[sp2:sp2 + cl2*2].decode('utf-16-le', errors='replace')
        if ename == 'manifest':
            print(f'Manifest element: attrCount={ac}')
            # Print attribute values
            for ai in range(ac):
                aoff = pos + 36 + ai * 20
                ans = struct.unpack_from('<i', patched, aoff)[0]
                aname = struct.unpack_from('<i', patched, aoff + 4)[0]
                araw = struct.unpack_from('<i', patched, aoff + 8)[0]
                atype = struct.unpack_from('<H', patched, aoff + 14)[0]
                adata = struct.unpack_from('<I', patched, aoff + 16)[0]
                # resolve name
                if aname >= 0 and aname < sp_string_count:
                    so = struct.unpack_from('<I', patched, offsets_start + aname * 4)[0]
                    pp = abs_strings_start + so
                    vv = struct.unpack_from('<H', patched, pp)[0]
                    if vv & 0x8000:
                        cll = ((vv & 0x7FFF) << 16) | struct.unpack_from('<H', patched, pp + 2)[0]
                        pp2 = pp + 4
                    else:
                        cll = vv; pp2 = pp + 2
                    nstr = patched[pp2:pp2 + cll*2].decode('utf-16-le', errors='replace')
                else:
                    nstr = f'idx={aname}'
                print(f'  attr[{ai}]: name={nstr} type=0x{atype:04x} data={adata}')
            break
    pos += cs

print('DONE')
