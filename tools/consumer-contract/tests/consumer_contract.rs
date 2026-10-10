use std::fs;

use rstest::rstest;
use tempfile::{TempDir, tempdir};
use vx_rez_adapter::{EnvAction, EnvDelta, Environment, ResolvedEnv};
use vx_runtime_consumer_contract::{ContractRequest, validate_resolution};

struct Fixture {
    _temporary: TempDir,
    request: ContractRequest,
    resolved: ResolvedEnv,
}

fn fixture() -> Fixture {
    let temporary = tempdir().unwrap();
    let repository = temporary.path().join("repository");
    let root = repository.join("fixture/1.2.3/platform-native/arch-native");
    let payload = root.join("payload");
    let bin = payload.join("bin");
    fs::create_dir_all(&bin).unwrap();
    let executable = bin.join(if cfg!(windows) {
        "fixture.exe"
    } else {
        "fixture"
    });
    fs::write(&executable, b"payload bytes inspected but not executed").unwrap();
    let environment = Environment::from([("PATH".to_string(), bin.to_str().unwrap().to_string())]);
    let platform = match std::env::consts::OS {
        "windows" => "windows",
        "macos" => "osx",
        _ => "linux",
    };
    let request = ContractRequest {
        schema_version: 1,
        repository: repository.clone(),
        tool: "fixture".to_string(),
        version: "1.2.3".to_string(),
        platform: platform.to_string(),
        arch: match std::env::consts::ARCH {
            "aarch64" => "arm_64",
            arch => arch,
        }
        .to_string(),
        expected_root: root.clone(),
        payload_root: payload,
        executable: executable.clone(),
        command: vec![
            executable.to_str().unwrap().to_string(),
            "--version".to_string(),
        ],
        expected_environment: environment.clone(),
        expected_sdk_version: Some("test-sdk".to_string()),
    };
    let mut generated = environment;
    generated.extend([
        ("REZ_USED_REQUEST".to_string(), "fixture-1.2.3".to_string()),
        (
            "REZ_USED_RESOLVE".to_string(),
            "platform-native arch-native fixture-1.2.3".to_string(),
        ),
        (
            "REZ_USED_PACKAGES_NAMES".to_string(),
            "platform-native arch-native fixture-1.2.3".to_string(),
        ),
        (
            "REZ_USED_PACKAGES_PATH".to_string(),
            repository.to_str().unwrap().to_string(),
        ),
        ("REZ_USED_VERSION".to_string(), "test-sdk".to_string()),
        (
            "REZ_USED_TIMESTAMP".to_string(),
            "test-timestamp".to_string(),
        ),
    ]);
    let mut delta = EnvDelta::new();
    for (key, value) in generated {
        delta.push_action(key, EnvAction::Set(value));
    }
    let mut resolved = ResolvedEnv::from_delta(delta, &Environment::new());
    resolved.package_roots.push(root);
    Fixture {
        _temporary: temporary,
        request,
        resolved,
    }
}

#[rstest]
fn test_validate_resolution_accepts_only_declared_package_environment_and_sdk_metadata() {
    let fixture = fixture();
    validate_resolution(&fixture.request, &fixture.resolved).unwrap();
}

#[rstest]
#[case("USER")]
#[case("HOME")]
#[case("SYSTEMROOT")]
#[case("VX_CONSUMER_PARENT_SENTINEL")]
#[case("REZ_UNLISTED_VARIABLE")]
fn test_validate_resolution_rejects_unexpected_keys_without_printing_values(#[case] key: &str) {
    let mut fixture = fixture();
    fixture
        .resolved
        .environment
        .insert(key.to_string(), "sensitive-parent-value".to_string());
    let error = validate_resolution(&fixture.request, &fixture.resolved)
        .unwrap_err()
        .to_string();
    assert!(error.contains(key));
    assert!(!error.contains("sensitive-parent-value"));
}

#[rstest]
fn test_validate_resolution_rejects_wrong_variant_root() {
    let mut fixture = fixture();
    fixture.resolved.package_roots = vec![fixture.request.repository.clone()];
    assert!(
        validate_resolution(&fixture.request, &fixture.resolved)
            .unwrap_err()
            .to_string()
            .contains("variant root")
    );
}

#[rstest]
fn test_validate_request_rejects_executable_outside_payload() {
    let mut fixture = fixture();
    let external = fixture.request.repository.join("outside.exe");
    fs::write(&external, b"outside").unwrap();
    fixture.request.executable = external.clone();
    fixture.request.command[0] = external.to_str().unwrap().to_string();
    assert!(
        fixture
            .request
            .validate()
            .unwrap_err()
            .to_string()
            .contains("leaves the selected payload")
    );
}

#[rstest]
fn test_validate_request_rejects_foreign_platform() {
    let mut fixture = fixture();
    fixture.request.platform = "foreign".to_string();
    assert!(
        fixture
            .request
            .validate()
            .unwrap_err()
            .to_string()
            .contains("foreign native platform")
    );
}

#[rstest]
fn test_validate_resolution_rejects_ambient_path_fallback() {
    let mut fixture = fixture();
    fixture
        .resolved
        .environment
        .insert("PATH".to_string(), "ambient-runtime-directory".to_string());
    assert!(
        validate_resolution(&fixture.request, &fixture.resolved)
            .unwrap_err()
            .to_string()
            .contains("environment value differs: PATH")
    );
}

#[rstest]
#[case("REZ_USED_REQUEST", "another-1.0")]
#[case("REZ_USED_VERSION", "wrong-sdk")]
#[case("REZ_USED_PACKAGES_NAMES", "another-1.0")]
fn test_validate_resolution_rejects_incorrect_sdk_binding(#[case] key: &str, #[case] value: &str) {
    let mut fixture = fixture();
    fixture
        .resolved
        .environment
        .insert(key.to_string(), value.to_string());
    assert!(
        validate_resolution(&fixture.request, &fixture.resolved)
            .unwrap_err()
            .to_string()
            .contains("metadata differs")
    );
}

#[rstest]
fn test_validate_resolution_rejects_delta_that_inherits_a_parent() {
    let mut fixture = fixture();
    fixture.resolved.delta = EnvDelta::new();
    assert!(
        validate_resolution(&fixture.request, &fixture.resolved)
            .unwrap_err()
            .to_string()
            .contains("exact empty-parent result")
    );
}

#[rstest]
fn test_validate_resolution_rejects_metadata_for_another_repository() {
    let mut fixture = fixture();
    fixture.resolved.environment.insert(
        "REZ_USED_PACKAGES_PATH".to_string(),
        fixture
            .request
            .repository
            .parent()
            .unwrap()
            .to_str()
            .unwrap()
            .to_string(),
    );
    assert!(
        validate_resolution(&fixture.request, &fixture.resolved)
            .unwrap_err()
            .to_string()
            .contains("repository metadata differs")
    );
}

#[rstest]
fn test_validate_resolution_supports_explicit_extra_package_variables() {
    let mut fixture = fixture();
    fixture
        .request
        .expected_environment
        .insert("PACKAGE_SETTING".to_string(), "declared".to_string());
    fixture
        .resolved
        .environment
        .insert("PACKAGE_SETTING".to_string(), "declared".to_string());
    fixture
        .resolved
        .delta
        .push_action("PACKAGE_SETTING", EnvAction::Set("declared".to_string()));
    validate_resolution(&fixture.request, &fixture.resolved).unwrap();
}
