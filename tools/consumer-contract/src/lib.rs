//! Native acceptance through the public adapter, with explicit activation expectations.

use std::collections::BTreeSet;
use std::io::{self, Write};
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};
use thiserror::Error;
use vx_rez_adapter::{
    Environment, LaunchRequest, ResolveRequest, ResolvedEnv, RezAdapter, env_key,
};

/// The exact SDK metadata contract; other variables require explicit package expectations.
pub const SDK_METADATA: [&str; 6] = [
    "REZ_USED_REQUEST",
    "REZ_USED_RESOLVE",
    "REZ_USED_PACKAGES_NAMES",
    "REZ_USED_PACKAGES_PATH",
    "REZ_USED_VERSION",
    "REZ_USED_TIMESTAMP",
];

/// Pinned repository and native smoke expectations supplied by the Python harness.
#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ContractRequest {
    /// Request wire format version.
    pub schema_version: u32,
    /// Already verified repository, isolated from the immutable cache.
    pub repository: PathBuf,
    /// Exact runtime identity from the manifest.
    pub tool: String,
    /// Upstream runtime version, independent of packaging revision.
    pub version: String,
    /// Native Rez platform.
    pub platform: String,
    /// Native Rez architecture.
    pub arch: String,
    /// Selected variant root identified by the manifest.
    pub expected_root: PathBuf,
    /// Full payload location identified by the manifest.
    pub payload_root: PathBuf,
    /// Exact native executable named by the smoke command.
    pub executable: PathBuf,
    /// Fully rendered native smoke command, preserving every argument.
    pub command: Vec<String>,
    /// Complete package environment expected after activation of an empty parent.
    pub expected_environment: Environment,
    /// Optional additional binding to the publicly published SDK version.
    pub expected_sdk_version: Option<String>,
}

/// A consumer contract failure, including native adapter diagnostics.
#[derive(Debug, Error)]
pub enum ContractError {
    /// A supplied expectation or resolved result violated the contract.
    #[error("consumer contract failed: {0}")]
    Invalid(String),
    /// A required path or output stream could not be inspected.
    #[error(transparent)]
    Io(#[from] io::Error),
    /// The public adapter could not resolve or launch the real package.
    #[error(transparent)]
    Adapter(#[from] vx_rez_adapter::Error),
}

/// Successful native acceptance, emitted after both launches terminate successfully.
#[derive(Debug, Serialize)]
pub struct Receipt {
    /// Receipt wire format version.
    pub schema_version: u32,
    /// The tested runtime family.
    pub tool: String,
    /// The tested upstream runtime version.
    pub version: String,
    /// The tested platform.
    pub platform: String,
    /// The tested architecture.
    pub arch: String,
    /// Core-selected variant root.
    pub selected_root: PathBuf,
    /// Verified payload executable.
    pub executable: PathBuf,
    /// SDK version read from its documented activation metadata.
    pub sdk_version: String,
    /// Complete resolved key set; values are not logged.
    pub environment_keys: Vec<String>,
    /// Both exact-path and bare-command smoke launches passed.
    pub launches: Vec<String>,
}

fn require(condition: bool, message: impl Into<String>) -> Result<(), ContractError> {
    if condition {
        Ok(())
    } else {
        Err(ContractError::Invalid(message.into()))
    }
}

fn canonical(path: &Path) -> Result<PathBuf, ContractError> {
    Ok(path.canonicalize()?)
}

impl ContractRequest {
    /// Validate binding and containment without executing package commands.
    pub fn validate(&self) -> Result<(), ContractError> {
        require(self.schema_version == 1, "unsupported request schema")?;
        let native_platform = match std::env::consts::OS {
            "windows" => "windows",
            "linux" => "linux",
            "macos" => "osx",
            _ => "unsupported",
        };
        require(self.platform == native_platform, "foreign native platform")?;
        let native_arch = match std::env::consts::ARCH {
            "x86_64" => "x86_64",
            "aarch64" => "arm_64",
            _ => "unsupported",
        };
        require(self.arch == native_arch, "foreign native architecture")?;
        for path in [
            &self.repository,
            &self.expected_root,
            &self.payload_root,
            &self.executable,
        ] {
            require(path.is_absolute(), "consumer paths must be absolute")?;
        }
        require(self.repository.is_dir(), "repository is absent")?;
        require(
            self.expected_root.is_dir(),
            "expected variant root is absent",
        )?;
        require(self.payload_root.is_dir(), "payload root is absent")?;
        require(self.executable.is_file(), "expected executable is absent")?;
        let repository = canonical(&self.repository)?;
        let root = canonical(&self.expected_root)?;
        let payload = canonical(&self.payload_root)?;
        let executable = canonical(&self.executable)?;
        require(
            root.starts_with(&repository),
            "variant root leaves the repository",
        )?;
        require(
            payload.parent() == Some(root.as_path()),
            "payload does not belong to the variant root",
        )?;
        require(
            payload.file_name().is_some_and(|name| name == "payload"),
            "payload root name is invalid",
        )?;
        require(
            executable.starts_with(&payload),
            "executable leaves the selected payload",
        )?;
        require(!self.command.is_empty(), "native smoke command is empty")?;
        require(
            Path::new(&self.command[0]).is_absolute(),
            "native smoke executable must be absolute",
        )?;
        require(
            canonical(Path::new(&self.command[0]))? == executable,
            "native smoke command does not name the expected executable",
        )?;
        require(
            !self.tool.is_empty() && !self.version.is_empty(),
            "runtime identity is empty",
        )?;
        Ok(())
    }
}

/// Check the complete environment and selected root returned by the public adapter.
pub fn validate_resolution(
    request: &ContractRequest,
    resolved: &ResolvedEnv,
) -> Result<(), ContractError> {
    request.validate()?;
    let expected_root = canonical(&request.expected_root)?;
    let selected = resolved
        .package_roots
        .iter()
        .map(|root| canonical(root))
        .collect::<Result<Vec<_>, _>>()?;
    require(
        selected.contains(&expected_root),
        "Core did not select the manifest's variant root",
    )?;
    let expected: Environment = request
        .expected_environment
        .iter()
        .map(|(key, value)| (env_key(key), value.clone()))
        .collect();
    require(
        expected.len() == request.expected_environment.len(),
        "expectation contains duplicate environment keys",
    )?;
    require(
        !expected.contains_key("VX_CONSUMER_PARENT_SENTINEL"),
        "parent sentinel cannot be an expected package variable",
    )?;
    require(
        !SDK_METADATA.iter().any(|key| expected.contains_key(*key)),
        "package expectations cannot replace SDK metadata",
    )?;
    let expected_keys: BTreeSet<_> = expected
        .keys()
        .cloned()
        .chain(SDK_METADATA.iter().map(|key| (*key).to_string()))
        .collect();
    let actual_keys: BTreeSet<_> = resolved.environment.keys().cloned().collect();
    if expected_keys != actual_keys {
        return Err(ContractError::Invalid(format!(
            "resolved environment keys differ: missing {:?}, unexpected {:?}",
            expected_keys.difference(&actual_keys).collect::<Vec<_>>(),
            actual_keys.difference(&expected_keys).collect::<Vec<_>>(),
        )));
    }
    for (key, value) in &expected {
        let actual = &resolved.environment[key];
        let matches = if key == "PATH" {
            std::env::split_paths(actual).collect::<Vec<_>>()
                == std::env::split_paths(value).collect::<Vec<_>>()
        } else {
            actual == value
        };
        require(
            matches,
            format!("resolved package environment value differs: {key}"),
        )?;
    }
    let path = resolved
        .environment
        .get("PATH")
        .ok_or_else(|| ContractError::Invalid("resolved PATH is absent".to_string()))?;
    let entries = std::env::split_paths(path).collect::<Vec<_>>();
    require(
        !entries.is_empty() && entries.iter().all(|entry| !entry.as_os_str().is_empty()),
        "resolved PATH contains empty entries",
    )?;
    require(
        entries
            .iter()
            .any(|entry| Some(entry.as_path()) == request.executable.parent()),
        "resolved PATH does not expose the expected executable directory",
    )?;
    for key in SDK_METADATA {
        require(
            !resolved.environment[key].is_empty(),
            format!("SDK metadata is empty: {key}"),
        )?;
    }
    let requirement = format!("{}-{}", request.tool, request.version);
    require(
        resolved.environment["REZ_USED_REQUEST"] == requirement,
        "SDK request metadata differs",
    )?;
    require(
        resolved.environment["REZ_USED_RESOLVE"] == resolved.environment["REZ_USED_PACKAGES_NAMES"],
        "SDK resolve metadata differs",
    )?;
    let repositories = std::env::split_paths(&resolved.environment["REZ_USED_PACKAGES_PATH"])
        .map(|path| canonical(&path))
        .collect::<Result<Vec<_>, _>>()?;
    require(
        repositories == [canonical(&request.repository)?],
        "SDK repository metadata differs",
    )?;
    if let Some(version) = &request.expected_sdk_version {
        require(
            resolved.environment["REZ_USED_VERSION"] == *version,
            "SDK version metadata differs",
        )?;
    }
    require(
        resolved.delta.apply(&Environment::new()) == resolved.environment,
        "adapter delta differs from its exact empty-parent result",
    )?;
    Ok(())
}

fn launch_phase(
    adapter: &RezAdapter,
    request: &ContractRequest,
    environment: &Environment,
    program: &Path,
    phase: &str,
) -> Result<(), ContractError> {
    println!("VX_REZ_CONSUMER_PHASE_BEGIN {phase}");
    io::stdout().flush()?;
    let outcome = adapter.launch(
        &LaunchRequest::new(program)
            .args(request.command.iter().skip(1).cloned())
            .environment(environment.clone())
            .working_dir(&request.expected_root),
    )?;
    require(
        outcome.success(),
        format!("{phase} smoke terminated unsuccessfully: {outcome:?}"),
    )?;
    println!("\nVX_REZ_CONSUMER_PHASE_END {phase}");
    io::stdout().flush()?;
    Ok(())
}

/// Resolve the unchanged real package and launch its exact and bare native smoke commands.
pub fn verify_and_launch(request: &ContractRequest) -> Result<Receipt, ContractError> {
    request.validate()?;
    let requirement = format!("{}-{}", request.tool, request.version);
    let resolve = ResolveRequest::new([requirement])
        .package_paths([&request.repository])
        .target(&request.platform, &request.arch)
        .parent_environment(Environment::new());
    let adapter = RezAdapter::new();
    let resolved = adapter.resolve_env(&resolve)?;
    validate_resolution(request, &resolved)?;
    launch_phase(
        &adapter,
        request,
        &resolved.environment,
        &request.executable,
        "direct",
    )?;
    let filename = if cfg!(windows)
        && request
            .executable
            .extension()
            .and_then(|extension| extension.to_str())
            .is_some_and(|extension| extension.eq_ignore_ascii_case("exe"))
    {
        request.executable.file_stem()
    } else {
        request.executable.file_name()
    }
    .ok_or_else(|| ContractError::Invalid("executable basename is absent".to_string()))?;
    launch_phase(
        &adapter,
        request,
        &resolved.environment,
        Path::new(filename),
        "bare",
    )?;
    Ok(Receipt {
        schema_version: 1,
        tool: request.tool.clone(),
        version: request.version.clone(),
        platform: request.platform.clone(),
        arch: request.arch.clone(),
        selected_root: request.expected_root.clone(),
        executable: request.executable.clone(),
        sdk_version: resolved.environment["REZ_USED_VERSION"].clone(),
        environment_keys: resolved.environment.keys().cloned().collect(),
        launches: vec!["direct".to_string(), "bare".to_string()],
    })
}
