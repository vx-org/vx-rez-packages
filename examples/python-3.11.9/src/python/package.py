name = "python"

version = "3.11.9"

description = "Sample Rez package used as a bundle format fixture."

authors = ["vx-org"]

requires = []

# The payload directory name carries the resolved version so a package root can
# be relocated without editing this file.
uuid = "vx-org.python.3.11.9"

def commands():
    """Rez commands contributed by this package.

    `env.PATH.prepend` puts the interpreter on PATH, and `alias` registers the
    Windows-only `pythonw` launcher when the payload provides it.
    """
    import os

    env.PATH.prepend("{root}")
    env.PYTHON_ROOT.set("{root}")
    env.PYTHON_VERSION.set(version)

    if os.path.exists(os.path.join(str(root), "pythonw.exe")):
        alias("pythonw", "pythonw.exe")
