#!/usr/bin/env python3
"""Decode a Google Drive connector download (JSON wrapper, base64 CSV) into a CSV file."""
import json, re, base64, sys, pandas as pd
def grab(fn, out):
    raw = open(fn, encoding='utf-8', errors='replace').read()
    try: txt = json.loads(raw)['content']
    except Exception:
        txt = json.loads('"' + re.search(r'"content"\s*:\s*"(.*)"\s*,\s*"id"', raw, re.S).group(1) + '"')
    body = re.sub(r'^#.*?\n', '', txt); body = re.sub(r'```', '', body).strip()
    if not re.match(r'^Timestamp', body):
        b64 = ''.join(re.findall(r'[A-Za-z0-9+/=]+', body))
        body = base64.b64decode(b64 + '=' * (-len(b64) % 4)).decode('utf-8', errors='replace')
    open(out, 'w', encoding='utf-8').write(body.replace('\r\n', '\n').strip() + '\n')
    d = pd.read_csv(out); d.columns = [c.strip() for c in d.columns]
    ts = pd.to_datetime(d[d.columns[0]], format='mixed', errors='coerce')
    print(f'{out}: {len(d)} rows, latest {ts.max()}')
if __name__ == '__main__': grab(sys.argv[1], sys.argv[2])
