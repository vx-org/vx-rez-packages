//! Compile-and-test harness for the REAL rez-next production `config.rs`.
//!
//! `config.rs` is not a port or a synthetic model: it is a verbatim copy of
//! rez-next `crates/rez-next-common/src/config.rs` at head `2405006` with only
//! the four PIP-4717 A source fixes applied (see `config_p3_fix.patch`). The
//! `#[path]` attribute compiles that file directly, so `cargo test` here runs
//! both the production test suite and the new A regression tests against the
//! real Rust implementation.
//!
//! `error`, `project` and `keys` are verbatim copies of the corresponding
//! production modules; they supply the only crate-internal items `config.rs`
//! references (`crate::error::RezCoreError`, `rez_next_config::project::*` and
//! `rez_next_config::keys::find`).

pub mod error;

#[path = "../../crates/rez-next-common/src/config.rs"]
mod config;

pub use config::*;
