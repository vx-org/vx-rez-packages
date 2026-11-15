name = "sample_zip"
version = "1.0.0"
description = "Minimal zip-archive pilot sample"

variants = [
    ["platform-windows", "arch-x86_64"],
    ["platform-linux", "arch-x86_64"],
]

build_command = "python {root}/build.py {install}"


def commands():
    env.PATH.prepend("{root}/payload/bin")
