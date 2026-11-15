"""Zip build strategy: fetch, verify, strip prefix, apply N mappings.

Exercises what rez-next's `binary_archive` cannot express: a leading-prefix
strip plus several independent mappings into a `payload/` layer, each with its
own executable flag. Under upstream rez none of this needs a build system —
`build_command` is the spec's extension point.
"""

import hashlib
import os
import shutil
import urllib.request
import zipfile

URL = "https://example.invalid/sample_zip-1.0.0-windows-x86_64.zip"
SHA256 = "<upstream digest>"

INSTALL = os.environ["REZ_BUILD_INSTALL_PATH"]
SOURCE = os.environ["REZ_BUILD_SOURCE_PATH"]

# 1. Fetch
archive = os.path.join(SOURCE, "payload.zip")
urllib.request.urlretrieve(URL, archive)

# 2. Verify integrity
with open(archive, "rb") as handle:
    digest = hashlib.sha256(handle.read()).hexdigest()
if digest != SHA256:
    raise SystemExit(f"sha256 mismatch: {digest} != {SHA256}")

# 3. Extract, strip the leading prefix, apply N mappings
PREFIX = "sample_zip-1.0.0/"
MAPPINGS = [
    ("bin/sample_zip.exe", "payload/bin/sample_zip.exe", True),
    ("lib", "payload/lib", False),
    ("share/doc", "payload/share/doc", False),
]

with zipfile.ZipFile(archive) as zf:
    zf.extractall(os.path.join(SOURCE, "extracted"))

extracted = os.path.join(SOURCE, "extracted", PREFIX)
for source, destination, executable in MAPPINGS:
    source_path = os.path.join(extracted, source)
    target_path = os.path.join(INSTALL, destination)
    if os.path.isdir(source_path):
        shutil.copytree(source_path, target_path, dirs_exist_ok=True)
    else:
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        shutil.copyfile(source_path, target_path)
    if executable:
        os.chmod(target_path, 0o755)
