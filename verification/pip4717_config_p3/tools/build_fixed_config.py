"""Derive the fixed production ``config.rs`` from the vendored pristine snapshot.

The PIP-4717 A findings concern the real Rust implementation in rez-next
``crates/rez-next-common/src/config.rs``. This script applies exactly those
four source fixes to a verbatim copy of that file at rez-next head
``240500672ec42c916aab35a8ae3a638c6e2d4302`` (the #380 merged head). Every
replacement is asserted to match exactly once, so a drift in the upstream
snapshot turns this into a hard failure instead of a silent partial patch.

The result is written to ``crates/rez-next-common/src/config.rs`` in this
harness. ``config_p3_fix.patch`` is the unified diff between the two files and
can be applied directly to a rez-next checkout.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRISTINE = (
    ROOT / "upstream" / "rez-next@2405006" / "crates" / "rez-next-common" / "src" / "config.rs"
)
FIXED = ROOT / "crates" / "rez-next-common" / "src" / "config.rs"

# A2: the old comment claimed rez-next's stderr report matched rez's hard
# failure. rez actually aborts on Setting.validate; rez-next reports and
# continues, so the equivalence claim is removed.
A2_OLD = """    /// A malformed override is a user-visible mistake and must not pass
    /// silently: rez raises `ConfigurationError` for the same condition
    /// (`src/rez/config.py`), and the config-file side of this loader already
    /// errors rather than falling back to defaults.
"""
A2_NEW = """    /// A malformed override is reported to stderr instead of failing hard:
    /// upstream rez raises `ConfigurationError` and aborts
    /// (`src/rez/config.py`), while rez-next keeps the previously loaded value
    /// and continues. The stderr report is not equivalent to rez's behaviour.
"""

# A3: drop the hand-maintained constant.
A3_CONST_OLD = """/// Nested keys accepted by [`CacheConfig`], used to reject unknown overrides
/// rather than silently ignoring them.
const CACHE_KEYS: [&str; 4] = [
    "enable_memory_cache",
    "enable_disk_cache",
    "memory_cache_size",
    "cache_ttl_seconds",
];

"""
A3_CONST_NEW = ""

# A3: derive the accepted-key wording from the serialized CacheConfig struct.
A3_HELPER_ANCHOR = """/// Assign an override to the nested `cache` object, merging it into the
/// existing value.
"""
A3_HELPER_NEW = """/// Render the accepted cache subkeys from the serialized [`CacheConfig`].
///
/// The unknown-key message must track the struct, not a hand-maintained list:
/// adding a field to `CacheConfig` changes its serialized object, so the
/// wording derived here changes with it instead of drifting silently.
fn expected_cache_keys(existing: &serde_json::Value) -> String {
    let mut keys: Vec<&str> = existing
        .as_object()
        .map(|map| map.keys().map(String::as_str).collect())
        .unwrap_or_default();
    keys.sort_unstable();
    keys.join(", ")
}

/// Assign an override to the nested `cache` object, merging it into the
/// existing value.
"""

A3_BODY_OLD = """    let existing = serde_json::to_value(&*target)
        .map_err(|e| format!("could not read current cache config ({e})"))?;
    let mut merged = existing;
"""
A3_BODY_NEW = """    let existing = serde_json::to_value(&*target)
        .map_err(|e| format!("could not read current cache config ({e})"))?;
    // Derive the accepted-key wording from the struct before `existing` moves.
    let expected = expected_cache_keys(&existing);
    let mut merged = existing;
"""

A3_MESSAGE_OLD = """                    return Err(format!(
                        "unknown cache key '{key}'; expected one of {}",
                        CACHE_KEYS.join(", ")
                    ));
"""
A3_MESSAGE_NEW = """                    return Err(format!(
                        "unknown cache key '{key}'; expected one of {expected}"
                    ));
"""

# A4: `load()` reads process-global REZ_* variables, so this test must hold
# ENV_LOCK just like every other environment-mutating test in the module.
A4_OLD = """    fn test_load_returns_config() {
        // Should not panic, even if no config file exists
        let cfg = RezCoreConfig::load();
        assert!(!cfg.version.is_empty());
    }
"""
A4_NEW = """    fn test_load_returns_config() {
        // Should not panic, even if no config file exists
        let _guard = env_lock();
        let cfg = RezCoreConfig::load();
        assert!(!cfg.version.is_empty());
    }
"""

NEW_TESTS = r"""
    // ---------------------------------------------------------------------
    // PIP-4717 A: named regression locks for the four override error branches
    // (A1), the stderr-report wording (A2), the struct-derived cache-key
    // message (A3) and the env lock in `test_load_returns_config` (A4).
    // ---------------------------------------------------------------------

    #[test]
    fn test_assign_cache_rejects_unknown_subkey_and_preserves_target() {
        let mut target = CacheConfig::default();
        target.memory_cache_size = 500;
        target.enable_disk_cache = false;
        let err = assign_cache(&mut target, &serde_json::json!({"typo": 1}))
            .expect_err("unknown cache subkey must be rejected");
        assert!(err.contains("unknown cache key 'typo'"), "{err}");
        // The malformed override must not silently reset the whole cache block.
        assert_eq!(target.memory_cache_size, 500);
        assert!(!target.enable_disk_cache);
    }

    #[test]
    fn test_assign_cache_rejects_non_object_and_preserves_target() {
        let mut target = CacheConfig::default();
        target.memory_cache_size = 500;
        target.enable_disk_cache = false;
        let err = assign_cache(&mut target, &serde_json::json!(7))
            .expect_err("a non-object cache override must be rejected");
        assert!(err.contains("invalid cache override"), "{err}");
        assert_eq!(target.memory_cache_size, 500);
        assert!(!target.enable_disk_cache);
    }

    #[test]
    fn test_assign_cache_partial_patch_keeps_sibling_keys() {
        // Control: the already-fixed P2 behaviour still holds. Not new P3
        // coverage; it guards against a fix that breaks the merge semantics.
        let mut target = CacheConfig::default();
        target.memory_cache_size = 500;
        target.enable_disk_cache = false;
        assign_cache(&mut target, &serde_json::json!({"memory_cache_size": 999}))
            .expect("a partial cache patch must apply");
        assert_eq!(target.memory_cache_size, 999);
        assert!(!target.enable_disk_cache);
    }

    #[test]
    fn test_assign_path_list_rejects_non_string_item_and_preserves_target() {
        let mut target = vec!["/keep".to_string()];
        let err = assign_path_list(&mut target, &serde_json::json!(["ok", 7]))
            .expect_err("a non-string path entry must be rejected");
        assert!(
            err.contains("expected every path entry to be a string"),
            "{err}"
        );
        assert_eq!(target, vec!["/keep".to_string()]);
    }

    #[test]
    fn test_assign_path_list_rejects_non_array_non_string_and_preserves_target() {
        let mut target = vec!["/keep".to_string()];
        let err = assign_path_list(&mut target, &serde_json::json!({"a": 1}))
            .expect_err("a mapping must not be accepted as a path list");
        assert!(err.contains("expected a path list, got mapping"), "{err}");
        assert_eq!(target, vec!["/keep".to_string()]);
    }

    #[test]
    fn test_expected_cache_keys_is_derived_from_serialized_struct() {
        let serialized = serde_json::to_value(CacheConfig::default()).unwrap();
        let derived = expected_cache_keys(&serialized);
        for key in serialized.as_object().unwrap().keys() {
            assert!(derived.contains(key.as_str()), "{derived} misses {key}");
        }
        // Simulate `CacheConfig` gaining a field: the wording must follow the
        // struct, not a hand-maintained constant. Reverting A3 to a hardcoded
        // list makes this assertion fail.
        let mut extended = serialized.as_object().unwrap().clone();
        extended.insert("new_cache_field".to_string(), serde_json::json!(0));
        let extended_value = serde_json::Value::Object(extended);
        assert!(
            expected_cache_keys(&extended_value).contains("new_cache_field"),
            "accepted-key wording is not derived from the struct"
        );
    }

    #[test]
    fn test_unknown_cache_key_message_lists_derived_keys() {
        let serialized = serde_json::to_value(CacheConfig::default()).unwrap();
        let expected = expected_cache_keys(&serialized);
        let err = assign_cache(
            &mut CacheConfig::default(),
            &serde_json::json!({"typo": 1}),
        )
        .expect_err("unknown cache subkey must be rejected");
        assert!(err.contains(&expected), "{err}");
    }

    #[test]
    fn test_report_comment_does_not_claim_rez_equivalence() {
        // A2 is a source-text property: lock the corrected wording in the real
        // Rust file so a regression back to the over-claim is caught by an
        // actual test rather than a README suggestion. The needles are split
        // with `concat!` so they do NOT appear contiguously inside this very
        // file (which `include_str!` reads back), otherwise the assertions
        // would trivially match their own literals.
        let source = include_str!("config.rs");
        let corrected = concat!(
            "A malformed override is reported to stderr instead of failing ",
            "hard"
        );
        assert!(source.contains(corrected), "A2 corrected wording is missing");
        let overclaim = concat!(
            "rez raises `ConfigurationError` for the same ",
            "condition"
        );
        assert!(
            !source.contains(overclaim),
            "A2 over-claim about rez equivalence is back"
        );
        let divergence = concat!(
            "The stderr report is not equivalent to rez's ",
            "behaviour."
        );
        assert!(
            source.contains(divergence),
            "A2 divergence statement is missing"
        );
    }

    #[test]
    fn test_load_returns_config_holds_env_lock() {
        // A4 is a source-text property of this test module: `load()` reads
        // process-global REZ_* variables, so `test_load_returns_config` must
        // hold ENV_LOCK. Removing the guard turns this assertion red.
        let source = include_str!("config.rs");
        let start = source
            .find("fn test_load_returns_config() {")
            .expect("test_load_returns_config must exist");
        let tail = &source[start..];
        let end = tail.find("\n    #[test]").unwrap_or(tail.len());
        let body = &tail[..end];
        assert!(
            body.contains("let _guard = env_lock();"),
            "test_load_returns_config must hold env_lock() around load()"
        );
    }
"""

REPLACEMENTS: tuple[tuple[str, str, str], ...] = (
    ("A2 comment", A2_OLD, A2_NEW),
    ("A3 drop hardcoded constant", A3_CONST_OLD, A3_CONST_NEW),
    ("A3 struct-derived helper", A3_HELPER_ANCHOR, A3_HELPER_NEW),
    ("A3 derive before move", A3_BODY_OLD, A3_BODY_NEW),
    ("A3 use derived wording", A3_MESSAGE_OLD, A3_MESSAGE_NEW),
    ("A4 env_lock in test_load_returns_config", A4_OLD, A4_NEW),
)


def main() -> None:
    text = PRISTINE.read_text(encoding="utf-8")
    for label, old, new in REPLACEMENTS:
        count = text.count(old)
        if count != 1:
            raise SystemExit(f"anchor mismatch for {label!r}: found {count} occurrences")
        text = text.replace(old, new, 1)
        print(f"applied: {label}")

    # Append the named regression tests just before the closing brace of
    # `mod tests` (the last line of the pristine file).
    closing = "}\n"
    if not text.endswith(closing):
        raise SystemExit("pristine config.rs does not end with the expected brace")
    if "fn test_assign_cache_rejects_unknown_subkey" in text:
        raise SystemExit("regression tests already present")
    text = text[: -len(closing)] + NEW_TESTS + closing
    print("applied: A1/A2/A3/A4 named regression tests")

    FIXED.parent.mkdir(parents=True, exist_ok=True)
    FIXED.write_text(text, encoding="utf-8")
    print(f"wrote: {FIXED} ({len(text.splitlines())} lines)")


if __name__ == "__main__":
    main()
