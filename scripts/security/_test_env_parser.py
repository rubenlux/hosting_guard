"""Fixture tests for the robust .env parser used in rotate_secrets_p4e.sh
and validate_secrets_hygiene.sh. Run with: python3 _test_env_parser.py"""
import re, sys

def parse_value(content, key):
    m = re.search(
        rf'^\s*(?:export\s+)?{re.escape(key)}\s*=\s*([^\r\n]*)',
        content, re.MULTILINE
    )
    if not m:
        return None
    return m.group(1).strip().strip('"').strip("'")

def rotate_key(content, key, new_val):
    new_content, count = re.subn(
        rf'^(\s*(?:export\s+)?{re.escape(key)}\s*=\s*)[^\r\n]*(\r?)$',
        rf'\g<1>{new_val}\g<2>',
        content, flags=re.MULTILINE
    )
    if count == 0:
        raise RuntimeError(f"{key} not found")
    return new_content

PARSE_FIXTURES = [
    ("KEY=value",           "JWT_SECRET=abc123\n",               "JWT_SECRET", "abc123"),
    ("export KEY=value",    "export JWT_SECRET=abc123\n",        "JWT_SECRET", "abc123"),
    ("leading spaces",      "  JWT_SECRET=abc123\n",             "JWT_SECRET", "abc123"),
    ("KEY = value",         "JWT_SECRET = abc123\n",             "JWT_SECRET", "abc123"),
    ("export + spaces",     "export JWT_SECRET = abc123\n",      "JWT_SECRET", "abc123"),
    ("quoted double",       'JWT_SECRET="abc123"\n',             "JWT_SECRET", "abc123"),
    ("quoted single",       "JWT_SECRET='abc123'\n",             "JWT_SECRET", "abc123"),
    ("CRLF ending",         "JWT_SECRET=abc123\r\nOTHER=x\r\n", "JWT_SECRET", "abc123"),
    ("comment before",      "# comment\nJWT_SECRET=abc123\n",   "JWT_SECRET", "abc123"),
    ("empty line before",   "\nJWT_SECRET=abc123\n",             "JWT_SECRET", "abc123"),
    ("multiple keys",       "X=1\nJWT_SECRET=abc123\nY=2\n",    "JWT_SECRET", "abc123"),
]

ROTATE_FIXTURES = [
    ("KEY=value preserves",     "JWT_SECRET=old\n",            "JWT_SECRET", "NEW", "JWT_SECRET="),
    ("export KEY preserves",    "export JWT_SECRET=old\n",     "JWT_SECRET", "NEW", "export JWT_SECRET="),
    ("leading space preserves", "  JWT_SECRET=old\n",          "JWT_SECRET", "NEW", "  JWT_SECRET="),
    ("KEY = value preserves",   "JWT_SECRET = old\n",          "JWT_SECRET", "NEW", "JWT_SECRET = "),
    ("CRLF preserved",          "JWT_SECRET=old\r\nX=1\r\n",  "JWT_SECRET", "NEW", "JWT_SECRET="),
    ("other keys untouched",    "X=1\nJWT_SECRET=old\nY=2\n", "JWT_SECRET", "NEW", None),
]

failures = 0

print("Parse fixtures:")
for desc, content, key, expected in PARSE_FIXTURES:
    val = parse_value(content, key)
    if val == expected:
        print(f"  [PASS] {desc}")
    else:
        print(f"  [FAIL] {desc}: got={repr(val)} expected={repr(expected)}")
        failures += 1

print("\nRotation fixtures:")
for desc, content, key, new_val, prefix_check in ROTATE_FIXTURES:
    try:
        rotated = rotate_key(content, key, new_val)
        val = parse_value(rotated, key)
        if val != new_val:
            print(f"  [FAIL] {desc}: value not rotated, got={repr(val)}")
            failures += 1
            continue
        if prefix_check is not None:
            line = next((l for l in rotated.splitlines()
                         if re.search(rf'^\s*(?:export\s+)?{re.escape(key)}\s*=', l)), "")
            if not line.startswith(prefix_check):
                print(f"  [FAIL] {desc}: prefix not preserved, line={repr(line)}")
                failures += 1
                continue
        if "other keys" in desc:
            if "X=1" not in rotated or "Y=2" not in rotated:
                print(f"  [FAIL] {desc}: other keys were modified")
                failures += 1
                continue
        print(f"  [PASS] {desc}")
    except Exception as e:
        print(f"  [FAIL] {desc}: exception: {e}")
        failures += 1

print(f"\n{'PASSED' if not failures else 'FAILED'} — {failures} failure(s)")
sys.exit(failures)
