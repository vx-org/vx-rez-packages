"""Bare-binary build strategy: fetch, verify, place.

Upstream rez has no archive or download primitive, so fetch / verify / place is
build-strategy code invoked through `build_command`. The sha256 digest has no
home in the rez package spec, so it lives here and in the publish-layer files.
"""

import hashlib
import os
import shutil
import urllib.request

URL = "https://example.invalid/sample_bin.exe"
SHA256 = "<upstream digest>"
INSTALL = os.environ["REZ_BUILD_INSTALL_PATH"]

# 1. Fetch
source = os.path.join(os.environ["REZ_BUILD_SOURCE_PATH"], "sample_bin.exe")
urllib.request.urlretrieve(URL, source)

# 2. Verify integrity
with open(source, "rb") as handle:
    digest = hashlib.sha256(handle.read()).hexdigest()
if digest != SHA256:
    raise SystemExit(f"sha256 mismatch: {digest} != {SHA256}")

# 3. Place under the variant's payload root
target = os.path.join(INSTALL, "payload", "bin", "sample_bin.exe")
os.makedirs(os.path.dirname(target), exist_ok=True)
shutil.copyfile(source, target)
os.chmod(target, 0o755)
