"""Bulk-upload every file in sample_docs/ to the running AssetMind backend."""
import os, sys, pathlib, urllib.request, urllib.error, json, mimetypes, uuid

API = "http://localhost:8000/api/documents/upload"
docs_dir = pathlib.Path(__file__).parent / "sample_docs"

def upload(filepath):
    boundary = uuid.uuid4().hex
    filename = filepath.name
    mime = mimetypes.guess_type(str(filepath))[0] or "application/octet-stream"
    data = filepath.read_bytes()

    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: {mime}\r\n\r\n"
    ).encode() + data + f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        API,
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read())
            print(f"  OK: {result.get('chunks_indexed',0)} chunks, ocr={result.get('ocr_used',False)}")
    except urllib.error.HTTPError as e:
        detail = json.loads(e.read()).get("detail", str(e))
        print(f"  FAIL ({e.code}): {detail}")
    except Exception as e:
        print(f"  ERROR: {e}")

files = sorted(docs_dir.iterdir())
print(f"Uploading {len(files)} documents from {docs_dir}\n")
for f in files:
    if f.is_file():
        print(f"Uploading {f.name}...")
        upload(f)
print("\nDone!")
