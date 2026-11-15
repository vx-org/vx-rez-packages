# Rez 3.4.0 — Authoritative Upstream Specification Baseline

**Purpose.** Normative reference of what upstream Rez *specifies*, so that other auditors can
compare a re-specification (e.g. `rez-next`) against it dimension by dimension.

**Source of truth.** A read-only shallow clone of upstream Rez
(`AcademySoftwareFoundation/rez`, branch `main`) at commit `f622b81`, version confirmed at
`src/rez/utils/_version.py:6` (`_rez_version = "3.4.0"`). The clone was a scratch working copy
and is not part of this repository.

**Citation discipline.** Every claim below carries a `src/...:LINE` (or `docs/...:LINE`) reference
to a file that was opened and read at that line. Where a concept is genuinely *not* in Rez, the
entry says `ABSENT — searched: <paths/patterns>` and records the search that was run. Nothing here
is inferred from memory or from a path that was not opened.

**Reading conventions used in this document**

* `src/...` paths are relative to the clone root; `docs/...` likewise.
* "Contract" means: the abstract base class, the methods a plugin must implement, and the
  mechanism by which Rez finds the plugin.
* `NotImplementedError` bodies are Rez's usual way of expressing "abstract" — **`src/rez/build_system.py`,
  `src/rez/package_repository.py`, `src/rez/release_vcs.py` and `src/rez/release_hook.py` do not use
  `abc.ABCMeta` / `@abstractmethod`**; they raise `NotImplementedError`. (By contrast
  `src/rez/package_resources.py:381`, `:385`, `:409`, `:414` *does* use `@abstractmethod`.)

**Global extension-point summary** (detail in §A.1): Rez 3.4.0 registers exactly **seven** plugin
types, at `src/rez/plugin_managers.py:543-549`: `shell`, `release_vcs`, `release_hook`,
`build_system`, `package_repository`, `build_process`, `command`.

---

