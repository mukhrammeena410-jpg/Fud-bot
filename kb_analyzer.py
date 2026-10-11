#!/usr/bin/env python3
"""kb_analyzer.py — Analyze APKs to extract patterns for the Knowledge Base.

Extracts encryption markers, poison entries, and wrapper structure from APKs
to build patterns that improve FUD generation.
"""
import hashlib
import logging
import os
import re
import struct
import zipfile
from pathlib import Path

logger = logging.getLogger("hathixfud-kb-analyzer")

# Known encryption markers in DEX/asset files
ENCRYPTION_MARKERS = [
    b"AES", b"GCM", b"CBC", b"PKCS5", b"PKCS7",
    b"javax.crypto", b"SecretKey", b"IvParameter",
    b"decrypt", b"encrypt",
]

# Known poison/junk entry patterns
POISON_PATTERNS = [
    r"^META-INF/.*\.(xml|png|9\.png)$",
    r"^kotlin/.*",
    r"^resources\.arsc/.*",
    r"^AndroidManifest\.xml/.*",
    r"^classes\.dex/.*",
    r"^\w+/\.(\w+/)*\w+\.(xml|png|9\.png|dex)$",
]


def analyze_apk(apk_path: str) -> dict:
    """Analyze an APK and extract all patterns for the KB.

    Returns a dict with categories: encryption, poison, wrapper.
    """
    result = {
        "encryption": [],
        "poison": [],
        "wrapper": [],
        "metadata": _extract_metadata(apk_path),
    }

    try:
        with zipfile.ZipFile(apk_path, "r") as zf:
            entries = zf.infolist()

            # Extract encryption patterns
            result["encryption"] = _extract_encryption_patterns(zf, entries)

            # Extract poison entry patterns
            result["poison"] = _extract_poison_patterns(entries)

            # Extract wrapper structure patterns
            result["wrapper"] = _extract_wrapper_patterns(zf, entries)

    except Exception as e:
        logger.error("Failed to analyze APK %s: %s", apk_path, e)

    return result


def _extract_metadata(apk_path: str) -> dict:
    """Extract basic metadata from APK."""
    return {
        "name": Path(apk_path).stem,
        "size": os.path.getsize(apk_path),
        "sha256": hashlib.sha256(open(apk_path, "rb").read()).hexdigest()[:16],
    }


def _extract_encryption_patterns(zf: zipfile.ZipFile, entries: list) -> list:
    """Extract encryption-related patterns from APK contents."""
    patterns = []

    for entry in entries:
        if entry.file_size == 0:
            continue

        # Check DEX files for encryption markers
        if entry.filename.endswith(".dex"):
            try:
                data = zf.read(entry.filename)
                markers_found = []
                for marker in ENCRYPTION_MARKERS:
                    if marker in data:
                        markers_found.append(marker.decode("utf-8", errors="ignore"))

                if markers_found:
                    patterns.append({
                        "type": "dex_encryption_marker",
                        "file": entry.filename,
                        "markers": markers_found,
                        "size": entry.size,
                    })

                # Check for encryption-related class names
                class_pattern = re.compile(rb"L[\w/]+(?:Cipher|Encrypt|Decrypt|Crypto|Security)[\w/]*;")
                matches = class_pattern.findall(data)
                if matches:
                    classes = [m.decode("utf-8", errors="ignore") for m in matches[:5]]
                    patterns.append({
                        "type": "encryption_classes",
                        "file": entry.filename,
                        "classes": classes,
                    })

            except Exception:
                pass

        # Check assets for encryption config
        if entry.filename.startswith("assets/"):
            try:
                data = zf.read(entry.filename)
                # Look for key/config files
                if entry.filename.endswith((".cfg", ".conf", ".properties", ".json")):
                    try:
                        text = data.decode("utf-8", errors="ignore")
                        if any(kw in text.lower() for kw in ["key", "encrypt", "secret", "token"]):
                            patterns.append({
                                "type": "asset_config",
                                "file": entry.filename,
                                "has_key_references": True,
                                "size": entry.size,
                            })
                    except Exception:
                        pass

                # Check for binary config patterns
                if len(data) >= 16:
                    # Look for repeated byte patterns (potential keys)
                    first_bytes = data[:32]
                    entropy = _calculate_entropy(first_bytes)
                    if entropy > 7:  # High entropy = likely encrypted/compressed
                        patterns.append({
                            "type": "high_entropy_asset",
                            "file": entry.filename,
                            "entropy": round(entropy, 2),
                            "size": entry.size,
                        })
            except Exception:
                pass

    return patterns


def _extract_poison_patterns(entries: list) -> list:
    """Extract poison/junk entry patterns from the APK."""
    patterns = []

    # Categorize entries
    suspicious = []
    normal = []
    for entry in entries:
        is_suspicious = False
        for pattern in POISON_PATTERNS:
            if re.match(pattern, entry.filename):
                is_suspicious = True
                break

        if is_suspicious:
            suspicious.append(entry)
        else:
            normal.append(entry)

    if suspicious:
        # Analyze suspicious entry naming patterns
        names = [e.filename for e in suspicious]
        extensions = [Path(n).suffix for n in names if "." in n]
        dirs = ["/".join(n.split("/")[:-1]) for n in names if "/" in n]

        patterns.append({
            "type": "suspicious_entries",
            "count": len(suspicious),
            "sample_names": names[:10],
            "extensions": list(set(extensions)),
            "directories": list(set(dirs))[:10],
            "sizes": [e.file_size for e in suspicious[:10]],
            "compression_flags": [e.compress_type for e in suspicious[:10]],
        })

    # Analyze entry size distribution
    all_sizes = [e.file_size for e in entries if e.file_size > 0]
    if all_sizes:
        patterns.append({
            "type": "size_distribution",
            "min_size": min(all_sizes),
            "max_size": max(all_sizes),
            "avg_size": round(sum(all_sizes) / len(all_sizes)),
            "total_entries": len(entries),
            "empty_entries": sum(1 for s in all_sizes if s == 0),
        })

    # Analyze compression patterns
    compressed = sum(1 for e in entries if e.compress_type == zipfile.ZIP_DEFLATED)
    stored = sum(1 for e in entries if e.compress_type == zipfile.ZIP_STORED)
    patterns.append({
        "type": "compression_ratio",
        "compressed": compressed,
        "stored": stored,
        "ratio": round(compressed / max(1, stored), 2),
    })

    return patterns


def _extract_wrapper_patterns(zf: zipfile.ZipFile, entries: list) -> list:
    """Extract wrapper structure patterns."""
    patterns = []

    # File ordering
    filenames = [e.filename for e in entries]
    patterns.append({
        "type": "file_ordering",
        "order": filenames,
        "total_files": len(filenames),
    })

    # Compression map
    compress_map = {}
    for entry in entries:
        compress_map[entry.filename] = entry.compress_type == zipfile.ZIP_DEFLATED
    patterns.append({
        "type": "compression_map",
        "map": compress_map,
    })

    # Resource structure
    res_files = [e for e in entries if e.filename.startswith("res/")]
    asset_files = [e for e in entries if e.filename.startswith("assets/")]
    patterns.append({
        "type": "resource_structure",
        "res_count": len(res_files),
        "asset_count": len(asset_files),
        "res_types": list(set(Path(e.filename).suffix for e in res_files)),
        "asset_types": list(set(Path(e.filename).suffix for e in asset_files)),
    })

    # Manifest analysis
    manifest = None
    for entry in entries:
        if entry.filename == "AndroidManifest.xml":
            manifest = entry
            break

    if manifest:
        try:
            data = zf.read(manifest.filename)
            patterns.append({
                "type": "manifest_info",
                "size": manifest.file_size,
                "binary_size": len(data),
                "is_binary": data[:4] == b"\x03\x00\x08\x00",
            })
        except Exception:
            pass

    return patterns


def _calculate_entropy(data: bytes) -> float:
    """Calculate Shannon entropy of data (0-8 scale)."""
    if not data:
        return 0.0

    freq = {}
    for byte in data:
        freq[byte] = freq.get(byte, 0) + 1

    entropy = 0.0
    length = len(data)
    for count in freq.values():
        p = count / length
        if p > 0:
            entropy -= p * __import__("math").log2(p)

    return entropy


def extract_patterns_for_kb(apk_path: str) -> list:
    """Extract patterns from APK and format them for KB insertion.

    Returns a list of (category, pattern_type, data) tuples.
    """
    analysis = analyze_apk(apk_path)
    kb_patterns = []

    # Encryption patterns
    for p in analysis["encryption"]:
        if p["type"] == "dex_encryption_marker":
            kb_patterns.append(("encryption", "markers", {
                "markers": p["markers"],
                "file": p["file"],
            }))
        elif p["type"] == "encryption_classes":
            kb_patterns.append(("encryption", "classes", {
                "classes": p["classes"],
            }))
        elif p["type"] == "high_entropy_asset":
            kb_patterns.append(("encryption", "entropy", {
                "file": p["file"],
                "entropy": p["entropy"],
            }))

    # Poison patterns
    for p in analysis["poison"]:
        if p["type"] == "suspicious_entries":
            kb_patterns.append(("poison", "entry_name", {
                "names": p["sample_names"],
                "extensions": p["extensions"],
                "directories": p["directories"],
            }))
            kb_patterns.append(("poison", "entry_size", {
                "sizes": p["sizes"],
                "avg": round(sum(p["sizes"]) / max(1, len(p["sizes"]))),
            }))
        elif p["type"] == "compression_ratio":
            kb_patterns.append(("poison", "compression_flag", {
                "compressed": p["compressed"],
                "stored": p["stored"],
                "ratio": p["ratio"],
            }))

    # NOTE: Wrapper patterns are NOT extracted from input APKs
    # The wrapper has a fixed structure that must not be changed
    # Only encryption and poison patterns are learned from input APKs

    return kb_patterns


# ----------------------------- Firebase & Key Extraction -----------------------------

def extract_firebase_and_keys(apk_path: str) -> dict:
    """Extract Firebase config and encryption keys from APK.

    Returns a dict with firebase config, API keys, auth tokens, database URLs, etc.
    """
    result = {
        "firebase": {},
        "keys": [],
        "urls": [],
        "package": "",
        "app_name": "",
    }

    try:
        with zipfile.ZipFile(apk_path, "r") as zf:
            # Extract package name from AndroidManifest.xml
            result["package"] = _extract_package_name(zf)

            # Extract app name from resources
            result["app_name"] = _extract_app_name(zf)

            # Look for google-services.json (Firebase config)
            for entry in zf.infolist():
                if "google-services.json" in entry.filename:
                    try:
                        data = zf.read(entry.filename)
                        result["firebase"] = _parse_google_services_json(data)
                    except Exception:
                        pass

                # Look for firebase config files
                if "firebase" in entry.filename.lower() and entry.filename.endswith((".json", ".xml", ".cfg")):
                    try:
                        data = zf.read(entry.filename)
                        config = _extract_firebase_config(data, entry.filename)
                        if config:
                            result["firebase"][entry.filename] = config
                    except Exception:
                        pass

                # Look for assets with keys/configs
                if entry.filename.startswith("assets/") and entry.file_size > 0:
                    try:
                        data = zf.read(entry.filename)
                        keys = _extract_keys_from_asset(data, entry.filename)
                        result["keys"].extend(keys)
                    except Exception:
                        pass

            # Extract from DEX files
            for entry in zf.infolist():
                if entry.filename.endswith(".dex") and entry.file_size > 0:
                    try:
                        data = zf.read(entry.filename)
                        keys = _extract_keys_from_dex(data)
                        result["keys"].extend(keys)
                    except Exception:
                        pass

            # Extract from XML files
            for entry in zf.infolist():
                if entry.filename.endswith(".xml") and entry.file_size > 0:
                    try:
                        data = zf.read(entry.filename)
                        urls = _extract_urls_from_xml(data)
                        result["urls"].extend(urls)
                    except Exception:
                        pass

            # Extract from strings in resources
            for entry in zf.infolist():
                if entry.filename == "resources.arsc" and entry.file_size > 0:
                    try:
                        data = zf.read(entry.filename)
                        keys = _extract_keys_from_resources(data)
                        result["keys"].extend(keys)
                    except Exception:
                        pass

    except Exception as e:
        logger.error("Failed to extract firebase/keys from %s: %s", apk_path, e)

    # Deduplicate
    result["keys"] = _deduplicate_keys(result["keys"])
    result["urls"] = list(set(result["urls"]))[:20]

    return result


def _extract_package_name(zf: zipfile.ZipFile) -> str:
    """Extract package name from AndroidManifest.xml binary."""
    try:
        for entry in zf.infolist():
            if entry.filename == "AndroidManifest.xml":
                data = zf.read(entry.filename)
                # Look for package name pattern in binary XML
                # Common pattern: com.xxx.xxx
                matches = re.findall(rb'com\.[a-zA-Z0-9_.]+', data)
                if matches:
                    # Return the most likely package name (longest match)
                    packages = [m.decode('utf-8', errors='ignore') for m in matches]
                    # Filter out short/invalid ones
                    valid = [p for p in packages if len(p) > 10 and '.' in p]
                    if valid:
                        return max(valid, key=len)
    except Exception:
        pass
    return ""


def _extract_app_name(zf: zipfile.ZipFile) -> str:
    """Extract app name from resources.arsc."""
    try:
        for entry in zf.infolist():
            if entry.filename == "resources.arsc" and entry.file_size > 0:
                data = zf.read(entry.filename)
                # Look for app name patterns
                # Common: strings that look like app names
                text = data.decode('utf-8', errors='ignore')
                # Find potential app names (capitalized words)
                matches = re.findall(r'([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)+)', text)
                if matches:
                    # Return the first reasonable app name
                    for m in matches:
                        if 3 < len(m) < 30:
                            return m
    except Exception:
        pass
    return ""


def _parse_google_services_json(data: bytes) -> dict:
    """Parse google-services.json for Firebase config."""
    import json
    result = {}
    try:
        config = json.loads(data.decode('utf-8'))

        # Extract project info
        if "project_info" in config:
            pi = config["project_info"]
            result["project_id"] = pi.get("project_id", "")
            result["project_number"] = pi.get("project_number", "")
            result["firebase_url"] = pi.get("firebase_url", "")
            result["storage_bucket"] = pi.get("storage_bucket", "")

        # Extract client info
        if "client" in config:
            for client in config["client"]:
                if "client_info" in client:
                    ci = client["client_info"]
                    result["mobilesdk_app_id"] = ci.get("mobilesdk_app_id", "")
                    result["android_client_info"] = ci.get("android_client_info", {})

                # Extract API keys
                if "api_key" in client:
                    for key in client["api_key"]:
                        if "current_key" in key:
                            result["api_key"] = key["current_key"]

                # Extract OAuth client ID
                if "oauth_client" in client:
                    for oauth in client["oauth_client"]:
                        if "client_id" in oauth:
                            result["oauth_client_id"] = oauth["client_id"]

    except Exception:
        pass
    return result


def _extract_firebase_config(data: bytes, filename: str) -> dict:
    """Extract Firebase config from XML/JSON files."""
    import json
    result = {}
    try:
        text = data.decode('utf-8', errors='ignore')

        # Try JSON first
        if text.strip().startswith('{'):
            config = json.loads(text)
            # Look for Firebase-related keys
            for key in ["apiKey", "authDomain", "databaseURL", "projectId",
                        "storageBucket", "messagingSenderId", "appId"]:
                if key in config:
                    result[key] = config[key]
        else:
            # XML format - look for Firebase values
            for key in ["api_key", "project_id", "firebase_url", "app_id"]:
                match = re.search(rf'{key}["\s:=]+([^"\'<>\s]+)', text, re.IGNORECASE)
                if match:
                    result[key] = match.group(1)
    except Exception:
        pass
    return result


def _extract_keys_from_asset(data: bytes, filename: str) -> list:
    """Extract potential keys from asset files."""
    keys = []

    # Look for common key patterns
    patterns = [
        (rb'["\']?api[_-]?key["\']?\s*[:=]\s*["\']([^"\']+)["\']', "API Key"),
        (rb'["\']?secret[_-]?key["\']?\s*[:=]\s*["\']([^"\']+)["\']', "Secret Key"),
        (rb'["\']?auth[_-]?token["\']?\s*[:=]\s*["\']([^"\']+)["\']', "Auth Token"),
        (rb'["\']?access[_-]?key["\']?\s*[:=]\s*["\']([^"\']+)["\']', "Access Key"),
        (rb'["\']?private[_-]?key["\']?\s*[:=]\s*["\']([^"\']+)["\']', "Private Key"),
        (rb'["\']?database[_-]?url["\']?\s*[:=]\s*["\']([^"\']+)["\']', "Database URL"),
        (rb'["\']?storage[_-]?bucket["\']?\s*[:=]\s*["\']([^"\']+)["\']', "Storage Bucket"),
        (rb'["\']?project[_-]?id["\']?\s*[:=]\s*["\']([^"\']+)["\']', "Project ID"),
        (rb'["\']?messaging[_-]?sender[_-]?id["\']?\s*[:=]\s*["\']([^"\']+)["\']', "Sender ID"),
    ]

    for pattern, key_type in patterns:
        matches = re.findall(pattern, data, re.IGNORECASE)
        for match in matches:
            value = match.decode('utf-8', errors='ignore').strip()
            if len(value) > 5 and len(value) < 200:
                keys.append({"type": key_type, "value": value, "file": filename})

    return keys


def _extract_keys_from_dex(data: bytes) -> list:
    """Extract potential keys from DEX files."""
    keys = []

    # Look for string literals that look like keys
    patterns = [
        (rb'["\']AIza[0-9A-Za-z_-]{30,}["\']', "Google API Key"),
        (rb'["\']eyJ[0-9A-Za-z_-]+\.eyJ[0-9A-Za-z_-]+["\']', "JWT Token"),
        (rb'["\']https?://[a-zA-Z0-9._/-]+\.firebaseio\.com["\']', "Firebase URL"),
        (rb'["\'][0-9a-f]{32,}["\']', "Possible Hash/Key"),
        (rb'["\'][a-zA-Z0-9]{20,40}["\']', "Possible Token"),
    ]

    for pattern, key_type in patterns:
        matches = re.findall(pattern, data)
        for match in matches:
            value = match.decode('utf-8', errors='ignore').strip('"\'')
            if len(value) > 10:
                keys.append({"type": key_type, "value": value, "file": "classes.dex"})

    return keys


def _extract_urls_from_xml(data: bytes) -> list:
    """Extract URLs from XML files."""
    urls = []
    try:
        text = data.decode('utf-8', errors='ignore')
        # Find URLs
        url_pattern = re.compile(r'https?://[a-zA-Z0-9._/-]+')
        matches = url_pattern.findall(text)
        for url in matches:
            if 'firebase' in url.lower() or 'google' in url.lower() or 'api' in url.lower():
                urls.append(url)
    except Exception:
        pass
    return urls


def _extract_keys_from_resources(data: bytes) -> list:
    """Extract potential keys from resources.arsc."""
    keys = []

    # Look for Firebase/Google patterns in the binary resources
    patterns = [
        (rb'firebaseio\.com', "Firebase URL"),
        (rb'googleapis\.com', "Google API"),
        (rb'AIza[0-9A-Za-z_-]{30,}', "Google API Key"),
    ]

    for pattern, key_type in patterns:
        matches = re.findall(pattern, data)
        for match in matches:
            value = match.decode('utf-8', errors='ignore')
            keys.append({"type": key_type, "value": value, "file": "resources.arsc"})

    return keys


def _deduplicate_keys(keys: list) -> list:
    """Remove duplicate keys."""
    seen = set()
    unique = []
    for key in keys:
        key_tuple = (key["type"], key["value"])
        if key_tuple not in seen:
            seen.add(key_tuple)
            unique.append(key)
    return unique


def format_firebase_report(apk_name: str, info: dict) -> str:
    """Format extracted Firebase/key info as a readable report."""
    lines = [
        f"📱 <b>APK Analysis: {apk_name}</b>",
        "━━━━━━━━━━━━━━━",
    ]

    if info.get("package"):
        lines.append(f"📦 Package: <code>{info['package']}</code>")
    if info.get("app_name"):
        lines.append(f"📛 App: <code>{info['app_name']}</code>")

    # Firebase config
    firebase = info.get("firebase", {})
    if firebase:
        lines.append("")
        lines.append("🔥 <b>Firebase Config:</b>")
        for key in ["project_id", "project_number", "firebase_url", "storage_bucket",
                     "api_key", "mobilesdk_app_id", "oauth_client_id"]:
            if key in firebase and firebase[key]:
                lines.append(f"• {key}: <code>{firebase[key]}</code>")

        # Also check nested firebase configs
        for fname, config in firebase.items():
            if isinstance(config, dict) and config:
                lines.append(f"\n📄 <b>{fname}:</b>")
                for k, v in config.items():
                    if v:
                        lines.append(f"• {k}: <code>{v}</code>")

    # Keys
    keys = info.get("keys", [])
    if keys:
        lines.append("")
        lines.append(f"🔑 <b>Keys Found: {len(keys)}</b>")
        for key in keys[:15]:  # Limit to 15 keys
            lines.append(f"• [{key['type']}] <code>{key['value'][:50]}</code>")
            if key.get("file"):
                lines.append(f"  📁 {key['file']}")

    # URLs
    urls = info.get("urls", [])
    if urls:
        lines.append("")
        lines.append(f"🔗 <b>Firebase/API URLs: {len(urls)}</b>")
        for url in urls[:10]:
            lines.append(f"• <code>{url}</code>")

    if not firebase and not keys and not urls:
        lines.append("")
        lines.append("ℹ️ No Firebase config or keys found.")

    return "\n".join(lines)

