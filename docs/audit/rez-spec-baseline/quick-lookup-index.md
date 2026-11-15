## Quick-lookup index

Flat `concept → src/...:LINE` list for fast citation. Paths are relative to the clone root.

```
### Version / baseline
Rez version string                        -> src/rez/utils/_version.py:6

### A. Build — plugin contract
build_system plugin dir                   -> src/rezplugins/build_system/  (cmake.py, custom.py, make.py, rezconfig.py)
cmake plugin class                        -> src/rezplugins/build_system/cmake.py:32
cmake plugin name()                       -> src/rezplugins/build_system/cmake.py:67-69
cmake configure step                      -> src/rezplugins/build_system/cmake.py:136-149
cmake build step                          -> src/rezplugins/build_system/cmake.py:207-236
cmake install step                        -> src/rezplugins/build_system/cmake.py:238-249
custom plugin class                       -> src/rezplugins/build_system/custom.py:33
custom plugin build()                     -> src/rezplugins/build_system/custom.py:107-237
custom build_command expansion            -> src/rezplugins/build_system/custom.py:148-161
custom parse_build_args.py hook           -> src/rezplugins/build_system/custom.py:82-105
make plugin STUB (NotImplementedError)    -> src/rezplugins/build_system/make.py:24
cmake plugin defaults (rezconfig)         -> src/rezplugins/build_system/rezconfig.py:8-35

BuildSystem base class                    -> src/rez/build_system.py:126
BuildResult TypedDict                     -> src/rez/build_system.py:25-28
BuildSystem.name (abstract)               -> src/rez/build_system.py:129-132
BuildSystem.__init__                      -> src/rez/build_system.py:134-171
BuildSystem.is_valid_root (abstract)      -> src/rez/build_system.py:173-176
BuildSystem.child_build_system            -> src/rez/build_system.py:178-191
BuildSystem.bind_cli                      -> src/rez/build_system.py:193-203
BuildSystem.build (abstract, core)        -> src/rez/build_system.py:205-239
BuildSystem.set_standard_vars             -> src/rez/build_system.py:241-303
BuildSystem.add_pre_build_commands        -> src/rez/build_system.py:305-340
BuildSystem.add_standard_build_actions    -> src/rez/build_system.py:342-358

get_buildsys_types()                      -> src/rez/build_system.py:31-34
get_valid_build_systems()                 -> src/rez/build_system.py:37-86
  build_command beats build_system        -> src/rez/build_system.py:62-65
  detection + child subtraction           -> src/rez/build_system.py:72-86
create_build_system()                     -> src/rez/build_system.py:89-123

### A. Build — extension points
extend_path (namespace merging)           -> src/rez/plugin_managers.py:44
namespace example                         -> src/rezplugins/command/__init__.py:5-6
load_plugins (both passes)                -> src/rez/plugin_managers.py:132-134
load_plugins_from_namespace               -> src/rez/plugin_managers.py:136-191
  custom paths win (reversed)             -> src/rez/plugin_managers.py:150-152
  skip _-prefixed / rezconfig             -> src/rez/plugin_managers.py:165-166
load_plugins_from_entry_points            -> src/rez/plugin_managers.py:193-214
  entry point group rez.plugins.<type>    -> src/rez/plugin_managers.py:194
register_plugin_module / register_plugin()-> src/rez/plugin_managers.py:234-247
load_config_from_plugin (rezconfig)       -> src/rez/plugin_managers.py:229-232
plugin config schema aggregation          -> src/rez/plugin_managers.py:288-293
RezPluginManager docstring (how-to)       -> src/rez/plugin_managers.py:300-352
plugin type registrations (7 types)       -> src/rez/plugin_managers.py:543-549
third-party plugin worked example         -> example_extensions/hello_cmd/rezplugins/command/world.py:33-41
example packaging                         -> example_extensions/hello_cmd/setup.py:8-15

### A. Build — package attributes
build_command schema                      -> src/rez/package_maker.py:88
build_system schema                       -> src/rez/package_maker.py:87
pre_build_commands (schema form)          -> src/rez/package_resources.py:160
pre_build_commands (POD form)             -> src/rez/package_maker.py:83
pre_build_commands (serialised form)      -> src/rez/package_serialise.py:99
package_build_only_keys (stripped)        -> src/rez/package_resources.py:42-48
package_rex_keys                          -> src/rez/package_resources.py:51-57
post_build_commands                       -> ABSENT (grep -rn "post_build_commands" src/)

### A. Build — env vars
REZ_BUILD_ENV                             -> src/rez/build_system.py:264
REZ_BUILD_PATH                            -> src/rez/build_system.py:265
REZ_BUILD_THREAD_COUNT                    -> src/rez/build_system.py:266
REZ_BUILD_VARIANT_INDEX                   -> src/rez/build_system.py:267
REZ_BUILD_VARIANT_REQUIRES                -> src/rez/build_system.py:268
REZ_BUILD_VARIANT_SUBPATH                 -> src/rez/build_system.py:269
REZ_BUILD_PROJECT_VERSION                 -> src/rez/build_system.py:270
REZ_BUILD_PROJECT_NAME                    -> src/rez/build_system.py:271
REZ_BUILD_PROJECT_DESCRIPTION             -> src/rez/build_system.py:272
REZ_BUILD_PROJECT_FILE                    -> src/rez/build_system.py:273
REZ_BUILD_SOURCE_PATH                     -> src/rez/build_system.py:274-278
REZ_BUILD_REQUIRES                        -> src/rez/build_system.py:279-283
REZ_BUILD_REQUIRES_UNVERSIONED            -> src/rez/build_system.py:284-288
REZ_BUILD_TYPE                            -> src/rez/build_system.py:289
REZ_BUILD_INSTALL                         -> src/rez/build_system.py:290
REZ_BUILD_INSTALL_PATH (conditional)      -> src/rez/build_system.py:293-294
REZ_IN_REZ_RELEASE (conditional, rez-1)   -> src/rez/build_system.py:296-299
BuildType enum (local=0, central=1)       -> src/rez/build_process.py:77-80
build env var docs                        -> docs/source/environment.rst:135-204
build_thread_count config                 -> src/rez/rezconfig.py:793
build_directory config                    -> src/rez/rezconfig.py:783
REZ_<SETTING> env override mechanism      -> src/rez/config.py:87-89

### A. Build — variants
variants schema                           -> src/rez/package_resources.py:178-182
variant requires composition              -> src/rez/packages.py:429-431
_variant subpath (default + hashed)       -> src/rez/package_resources.py:493-521
  hashed = sha1 hexdigest                 -> src/rez/package_resources.py:497-500
  default = join of safe_str() reqs       -> src/rez/package_resources.py:518-521
VariantResource.subpath property          -> src/rez/package_resources.py:371-379
VariantResourceHelper._root               -> src/rez/package_resources.py:523-529
Variant._non_shortlinked_subpath          -> src/rez/packages.py:486-488
hashed_variants attribute                 -> src/rez/package_resources.py:147
platform/arch/os variant convention       -> docs/source/variants.rst:106-124
variant disk layout example               -> docs/source/variants.rst:53-56
variant_shortlinks_dirname config         -> src/rez/rezconfig.py:816
use_variant_shortlinks docs               -> src/rez/rezconfig.py:818-821
shortlink creation during install         -> src/rezplugins/build_process/local.py:193-218
resolve_variant_indices (negatives)       -> src/rez/util.py:195-215
visit_variants                            -> src/rez/build_process.py:210-239
variant build/install path computation    -> src/rezplugins/build_process/local.py:157-166
subpath formatting in utils/formatting.py -> ABSENT (read outline; no subpath symbol)

### A. Build — requires
requires / build_requires / private_build_requires -> src/rez/package_resources.py:131-134
Variant.get_requires()                    -> src/rez/packages.py:433-452
build context uses all three              -> src/rez/build_process.py:259-260
build_requires NOT stripped on install    -> src/rez/package_resources.py:42-48

### A. Build — CLI
rez build setup_parser                    -> src/rez/cli/build.py:87-110
  -c/--clean                              -> src/rez/cli/build.py:88-90
  -i/--install                            -> src/rez/cli/build.py:91-94
  -p/--prefix                             -> src/rez/cli/build.py:95-97
  --fail-graph                            -> src/rez/cli/build.py:98-101
  -s/--scripts                            -> src/rez/cli/build.py:102-106
  --view-pre                              -> src/rez/cli/build.py:107-109
setup_parser_common (shared w/ release)   -> src/rez/cli/build.py:35-84
  --process                               -> src/rez/cli/build.py:43-46
  -b/--build-system                       -> src/rez/cli/build.py:67-71
  --variants                              -> src/rez/cli/build.py:73-76
  --ba/--build-args                       -> src/rez/cli/build.py:77-80
  --cba/--child-build-args                -> src/rez/cli/build.py:81-84
rez build --release / --paths / --keep-tmp / --extra-packages / --view-post -> ABSENT (see §A.6.3)

### A. Build — process model
BuildProcess base                         -> src/rez/build_process.py:83
BuildProcess.build (abstract)             -> src/rez/build_process.py:147-169
BuildProcess.release (abstract)           -> src/rez/build_process.py:171-188
BuildProcessHelper                        -> src/rez/build_process.py:199
create_build_process()                    -> src/rez/build_process.py:42-74
LocalBuildProcess.build()                 -> src/rezplugins/build_process/local.py:60-88
_build_variant_base (the step sequence)   -> src/rezplugins/build_process/local.py:149-305
  pre_variant_install                     -> src/rezplugins/build_process/local.py:186-189
  variant re-evaluation (building=True)   -> src/rezplugins/build_process/local.py:220-234
  create_build_context + build.rxt        -> src/rezplugins/build_process/local.py:237-240
  build_system.build() invocation         -> src/rezplugins/build_process/local.py:264-274
  failure -> rmtree + BuildError          -> src/rezplugins/build_process/local.py:276-281
  extra files + include modules           -> src/rezplugins/build_process/local.py:283-305
_build_variant (tests, variant.install)   -> src/rezplugins/build_process/local.py:340-392
BuildStep enum/objects                    -> ABSENT (grep -rn "BuildStep" src/ docs/)

### A. Build — remote
remote build process STUB                 -> src/rezplugins/build_process/remote.py:21, :24
remote register_plugin                    -> src/rezplugins/build_process/remote.py:27-28
"only local available" config comment     -> src/rez/rezconfig.py:824-825
default_build_process config              -> src/rez/rezconfig.py:828

### A. Build — timestamp
timestamp written on install              -> src/rezplugins/package_repository/filesystem.py:1433-1435
timestamp schema                          -> src/rez/package_resources.py:164
package_release_keys                      -> src/rez/package_resources.py:32-39
overrides precedence (new vs existing pkg)-> src/rezplugins/package_repository/filesystem.py:1423-1431
Variant.install(overrides=...)            -> src/rez/packages.py:454-484
PackageRepository.remove sentinel         -> src/rez/package_repository.py:79
rez-1 release_time.txt migration          -> src/rezplugins/package_repository/filesystem.py:233-238
build_time field                          -> ABSENT (grep -rn "build_time" src/; only vendored distlib)

### B. Test
rez test setup_parser                     -> src/rez/cli/test.py:11-44
  --dry-run                               -> src/rez/cli/test.py:15-18
  --stop-on-fail                          -> src/rez/cli/test.py:19-21
  --inplace                               -> src/rez/cli/test.py:22-25
  --extra-packages                        -> src/rez/cli/test.py:26-28
  --paths                                 -> src/rez/cli/test.py:29-31
  --no-local                              -> src/rez/cli/test.py:32-34
rez test --no-safe / --clean              -> ABSENT (see §B.10)
PackageTestRunner                         -> src/rez/package_test.py:22
PackageTestRunner docstring (tests dict)  -> src/rez/package_test.py:22-51
PackageTestRunner.__init__                -> src/rez/package_test.py:52-103
  common timestamp across tests           -> src/rez/package_test.py:101-103
get_package_test_names (run_on filter)    -> src/rez/package_test.py:141-193
run_test (exit-code semantics)            -> src/rez/package_test.py:252-502
  non-zero => failed, first propagated    -> src/rez/package_test.py:472-489
  dry-run => skipped                      -> src/rez/package_test.py:439-446
pre_test_commands execution               -> src/rez/package_test.py:448-462
_get_test_info                            -> src/rez/package_test.py:542-584
_get_context (testing=True, caching)      -> src/rez/package_test.py:586-634
PackageTestResults                        -> src/rez/package_test.py:677
rez:setup / rez:test / rez:teardown       -> ABSENT (grep -rn "rez:setup\|rez:test\|rez:teardown" .)
pytest/unittest framework detection       -> ABSENT (only docstring example src/rez/package_test.py:32)
tests schema                              -> src/rez/package_resources.py:101-121
tests attribute binding                   -> src/rez/package_resources.py:154
_run_tests (post-install tests)           -> src/rezplugins/build_process/local.py:449-519
  pre_install trigger (rez build)         -> src/rezplugins/build_process/local.py:374-379
  pre_release trigger (rez release)       -> src/rezplugins/build_process/local.py:428-433
  _redirected_base temp repo trick        -> src/rezplugins/build_process/local.py:484-489
  failure => PackageTestError             -> src/rezplugins/build_process/local.py:514-519
REZ_TEST_* env vars                       -> ABSENT (grep -rn "REZ_TEST" src/)

### C. Release
rez release setup_parser                  -> src/rez/cli/release.py:15-42
  -m/--message                            -> src/rez/cli/release.py:20-22
  --vcs                                   -> src/rez/cli/release.py:23-25
  --no-latest                             -> src/rez/cli/release.py:26-28
  --ignore-existing-tag                   -> src/rez/cli/release.py:29-33
  --skip-repo-errors                      -> src/rez/cli/release.py:34-38
  --no-message                            -> src/rez/cli/release.py:39-41
rez release --dry-run                     -> ABSENT (API-only: src/rez/packages.py:454-467)
release message prompting                 -> src/rez/cli/release.py:82-140
prompt_release_message config             -> src/rez/rezconfig.py:804

release phases (LocalBuildProcess.release)-> src/rezplugins/build_process/local.py:90-147
  pre_release validation                  -> src/rez/build_process.py:301-347
    release path exists                   -> src/rez/build_process.py:304-307
    vcs.validate_repostate                -> src/rez/build_process.py:310-313
    existing-tag check                    -> src/rez/build_process.py:315-326
    UUID mismatch check                   -> src/rez/build_process.py:328-337
    ensure_latest check                   -> src/rez/build_process.py:339-347
  get_release_data                        -> src/rez/build_process.py:414-448
  run_hooks(pre_release)                  -> src/rezplugins/build_process/local.py:103-109
  _release_variant                        -> src/rezplugins/build_process/local.py:394-447
  run_hooks(post_release)                 -> src/rezplugins/build_process/local.py:122-128
  post_release (tag)                      -> src/rez/build_process.py:349-357
repo_operation (error swallowing)         -> src/rez/build_process.py:202-208

release_vcs plugins                       -> src/rezplugins/release_vcs/ (git.py, hg.py, svn.py, stub.py)
GitReleaseVCS                             -> src/rezplugins/release_vcs/git.py:21
HgReleaseVCS                              -> src/rezplugins/release_vcs/hg.py:18
SvnReleaseVCS                             -> src/rezplugins/release_vcs/svn.py:60
StubReleaseVCS                            -> src/rezplugins/release_vcs/stub.py:16
create_release_vcs (closest root wins)    -> src/rez/release_vcs.py:23-69
ReleaseVCS base                           -> src/rez/release_vcs.py:72
  name (abstract)                         -> src/rez/release_vcs.py:91-94
  is_valid_root (abstract)                -> src/rez/release_vcs.py:104-113
  search_parents_for_root (abstract)      -> src/rez/release_vcs.py:115-120
  validate_repostate (abstract)           -> src/rez/release_vcs.py:142-144
  get_current_revision (abstract)         -> src/rez/release_vcs.py:146-155
  get_changelog (abstract)                -> src/rez/release_vcs.py:157-172
  tag_exists (abstract)                   -> src/rez/release_vcs.py:174-183
  create_release_tag (abstract)           -> src/rez/release_vcs.py:185-195
  export (abstract)                       -> src/rez/release_vcs.py:197-209
git validate_repostate                    -> src/rezplugins/release_vcs/git.py:93-142
git get_current_revision                  -> src/rezplugins/release_vcs/git.py:166-200
git get_changelog                         -> src/rezplugins/release_vcs/git.py:144-164

tag_name config (default {qualified_name}) -> src/rezplugins/release_vcs/rezconfig.py:12
tag_name docstring / warning              -> src/rezplugins/release_vcs/rezconfig.py:5-11
check_tag config (default False)          -> src/rezplugins/release_vcs/rezconfig.py:42
releasable_branches config                -> src/rezplugins/release_vcs/rezconfig.py:14-19
git allow_no_upstream                     -> src/rezplugins/release_vcs/rezconfig.py:44-47
get_current_tag_name()                    -> src/rez/build_process.py:359-367
tag_exists (git)                          -> src/rezplugins/release_vcs/git.py:202-204
create_release_tag no-op if exists (git)  -> src/rezplugins/release_vcs/git.py:206-208
create_release_tag no-op if exists (stub) -> src/rezplugins/release_vcs/stub.py:62-64

release_hook plugins                      -> src/rezplugins/release_hook/ (amqp.py, command.py, emailer.py)
AmqpReleaseHook                           -> src/rezplugins/release_hook/amqp.py:17
CommandReleaseHook                        -> src/rezplugins/release_hook/command.py:24
EmailReleaseHook                          -> src/rezplugins/release_hook/emailer.py:19
ReleaseHook base                          -> src/rez/release_hook.py:39
  name (abstract)                         -> src/rez/release_hook.py:46-49
  __init__ (reads own settings)           -> src/rez/release_hook.py:51-60
  pre_build                               -> src/rez/release_hook.py:62-84
  pre_release                             -> src/rez/release_hook.py:86-110
  post_release                            -> src/rez/release_hook.py:112-131
ReleaseHookEvent enum                     -> src/rez/release_hook.py:134-143
run_hooks                                 -> src/rez/build_process.py:369-388
release_hooks config                      -> src/rez/rezconfig.py:800

release_message schema                    -> src/rez/package_resources.py:167
release_packages_path config              -> src/rez/rezconfig.py:73
local_packages_path config                -> src/rez/rezconfig.py:69
packages_path config                      -> src/rez/rezconfig.py:62-67
nonlocal_packages_path usage              -> src/rez/build_process.py:266-269

### D. Repository & distribution
package_repository plugins (only 2)       -> src/rezplugins/package_repository/ (filesystem.py, memory.py)
FileSystemPackageRepository               -> src/rezplugins/package_repository/filesystem.py:438
  name()                                  -> src/rezplugins/package_repository/filesystem.py:490-492
  resource classes                        -> .../filesystem.py:93, :140, :272, :288, :353, :416
  schema_dict                             -> .../filesystem.py:474-477
  register_plugin()                       -> .../filesystem.py:1545-1546
MemoryPackageRepository                   -> src/rezplugins/package_repository/memory.py:115
package_repository rezconfig              -> src/rezplugins/package_repository/rezconfig.py:5-47
get_package_repository_types()            -> src/rez/package_repository.py:26-28
PackageRepositoryGlobalStats              -> src/rez/package_repository.py:46
PackageRepository base                    -> src/rez/package_repository.py:69
  remove sentinel                         -> src/rez/package_repository.py:79
  name (abstract)                         -> src/rez/package_repository.py:82
  get_package_family (abstract)           -> src/rez/package_repository.py:143
  iter_package_families (abstract)        -> src/rez/package_repository.py:154
  iter_packages (abstract)                -> src/rez/package_repository.py:163
  iter_variants (abstract)                -> src/rez/package_repository.py:175
  ignore_package (abstract)               -> src/rez/package_repository.py:230
  unignore_package (abstract)             -> src/rez/package_repository.py:249
  remove_package (abstract)               -> src/rez/package_repository.py:262
  remove_package_family (abstract)        -> src/rez/package_repository.py:277
  remove_ignored_since (abstract)         -> src/rez/package_repository.py:289
  install_variant (abstract)              -> src/rez/package_repository.py:330-333
  get_package_payload_path (abstract)     -> src/rez/package_repository.py:499
PackageRepositoryManager                  -> src/rez/package_repository.py:526
  URI '@' split + filesystem default      -> src/rez/package_repository.py:562-576
  _get_repository                         -> src/rez/package_repository.py:652-656
package_repository_manager singleton      -> src/rez/package_repository.py:660
Package / Variant classes                 -> src/rez/packages.py:203 / :342
resource classes                          -> src/rez/package_resources.py:275, :315, :324, :346, :397, :470
'|' options separator in repo URIs        -> ABSENT (grep -rn "split('|')" src/rez/)

package_filter classes                    -> src/rez/package_filter.py:21, :97, :234, :333, :436, :455, :473, :491, :519
package_filter config key                 -> src/rez/config.py:535 (default src/rez/rezconfig.py:453)
package_order classes                     -> src/rez/package_order.py:53, :205, :243, :297, :415, :468, :635
get_orderer (default version descending)  -> src/rez/package_order.py:739-748
register_orderer                          -> src/rez/package_order.py:751-765
package_orderers config key               -> src/rez/config.py:536 (default src/rez/rezconfig.py:459)
package_order config key                  -> ABSENT (grep -rn '"package_order"' src/)
package_filter/order plugin types         -> ABSENT (grep -n "package_filter\|package_order" src/rez/plugin_managers.py)

rez cp flags                              -> src/rez/cli/cp.py:12-62
rez mv flags                              -> src/rez/cli/mv.py:12-27
rez rm flags                              -> src/rez/cli/rm.py:15-36
copy_package()                            -> src/rez/package_copy.py:31-44
  keep_timestamp injection                -> src/rez/package_copy.py:236-237
move_package() (copy + hide)              -> src/rez/package_move.py:13-14, :17-19, :56-85
remove_package_family()                   -> src/rez/package_remove.py:13
remove_package()                          -> src/rez/package_remove.py:31
remove_packages_ignored_since()           -> src/rez/package_remove.py:53-54

memcached_uri config                      -> src/rez/config.py:425 (default src/rez/rezconfig.py:170)
resolve_caching / cache_package_files / cache_listdir -> src/rez/config.py:493 / :494 / :495
resource_caching_maxsize                  -> src/rez/config.py:474
rez memcache flags                        -> src/rez/cli/memcache.py:12-29
memcached Client                          -> src/rez/utils/memcached.py:26
memcached() decorator                     -> src/rez/utils/memcached.py:272-273
pool_memcached_connections()              -> src/rez/utils/memcached.py:253
cache_packages_path config                -> src/rez/config.py:438 (default src/rez/rezconfig.py:268)
Resource / ResourceHandle / ResourcePool  -> src/rez/utils/resources.py:56 / :152 / :204
  LRU wiring                              -> src/rez/utils/resources.py:212-215
load_resource / CachedFile                -> ABSENT (grep -rn "load_resource\|CachedFile" src/)
PackageCache                              -> src/rez/package_cache.py:39
rez pkg-cache flags                       -> src/rez/cli/pkg-cache.py:16-68
package_cache_* config keys               -> src/rez/config.py:482-491

### E. Ecosystem surface
rez bind CLI                              -> src/rez/cli/bind.py:42
bind_package engine                       -> src/rez/package_bind.py:81
bind module exec (not import)             -> src/rez/package_bind.py:160-162
bind dependency recursion                 -> src/rez/package_bind.py:134-138
bind modules (src/rez/bind/)              -> arch:14, platform:14, os:14, python:40, rez:21, rezgui:35,
                                             pip:11, setuptools:11, sip:12, PyQt:12, PySide:11,
                                             cmake:25, gcc:25, hello_world:43, _pymodule.py:59
rez pip CLI                               -> src/rez/cli/pip.py:39
pip_install_package                       -> src/rez/pip.py:239
pip invoked as `python -m pip`            -> src/rez/pip.py:57
distlib DistributionPath enumeration      -> src/rez/pip.py:321-323
pip package make_package + hashed_variants-> src/rez/pip.py:406, :432-435
pip provenance attrs (from_pip, ...)      -> src/rez/pip.py:438-440
pip name/version translation              -> src/rez/utils/pip.py:44 / :46
rez env CLI                               -> src/rez/cli/env.py:147
rez env flags                             -> src/rez/cli/env.py:20-133 (table in §E.23)
rez env --suite/--create/--no-rez-env     -> ABSENT (see §E.23)
rez context CLI                           -> src/rez/cli/context.py:112
ResolvedContext to_dict / from_dict       -> src/rez/resolved_context.py:1604 / :1704
context save / load                       -> src/rez/resolved_context.py:724 / :766
context format sniff (json vs yaml)       -> src/rez/resolved_context.py:2043-2047
rez suite CLI                             -> src/rez/cli/suite.py:89
Suite class                               -> src/rez/suite.py:48
Suite.save (suite.yaml)                   -> src/rez/suite.py:477
Suite.load                                -> src/rez/suite.py:517-521
suite tool wrapper generation             -> src/rez/suite.py:509-515
suite tool invocation entry               -> src/rez/suite.py:787
SuiteVisibility enum                      -> src/rez/resolved_context.py:82
suite_visibility config                   -> src/rez/config.py:434
`.rez` suite file                         -> ABSENT (suite.yaml only)
shell plugins                             -> src/rezplugins/shell/ (sh:23, bash:18, zsh:22, csh:25,
                                             tcsh:18, cmd:22, powershell:11, pwsh:11, gitbash:23)
Shell base class                          -> src/rez/shells.py:74
  schema_dict                             -> src/rez/shells.py:77
  name / file_extension / get_syspaths    -> src/rez/shells.py:79 / :113 / :139
  startup_capabilities / spawn_shell      -> src/rez/shells.py:122 / :213
  join (concrete default)                 -> src/rez/shells.py:314
UnixShell base                            -> src/rez/shells.py:344
ActionInterpreter (env verb contract)     -> src/rez/rex.py:454
  setenv / unsetenv / resetenv            -> src/rez/rex.py:501 / :504 / :507
  prependenv / appendenv                  -> src/rez/rex.py:510 / :515
  alias / source / command / shebang      -> src/rez/rex.py:520 / :535 / :529 / :538
  escape_string (no-op default)           -> src/rez/rex.py:546, :566
get_shell_types / create_shell            -> src/rez/shells.py:32 / :58
get_rezenv_*                              -> ABSENT (grep -rn "get_rezenv" src/)
rez yaml2py                               -> src/rez/cli/yaml2py.py:18
rez plugins                               -> src/rez/cli/plugins.py:24
rez-depends                               -> src/rez/cli/depends.py:45 (entry point _entry_points.py:130)
rez-search                                -> src/rez/cli/search.py:69 (entry point _entry_points.py:214)
rez config                                -> src/rez/cli/config.py:33
  --search-list / --source-list           -> src/rez/cli/config.py:18 / :22
  --list / --plugins / --plugin-config-data / --validate-config-file -> ABSENT
rez status                                -> src/rez/cli/status.py:26
Status class                              -> src/rez/status.py:23
rez help                                  -> src/rez/cli/help.py:28
PackageHelp                               -> src/rez/package_help.py:20

### E. Command surface
subcommand registry                       -> src/rez/cli/_util.py:24-73
subcommand -> module mapping               -> src/rez/cli/_main.py:111-117
rez foo / rez-foo equivalence             -> src/rez/cli/_main.py:130-137
console_scripts generation                -> src/rez/cli/_entry_points.py:15-40
console_scripts wiring (setup.py only)    -> setup.py:62-64
pyproject.toml entry points               -> ABSENT (searched pyproject.toml)
deprecated commands                       -> ABSENT (src/rez/deprecations.py: config-only, :9 / :36)

### F. Prebuilt / provenance / reproducibility
prebuilt-binary mechanism                 -> custom build system + build_command:
                                             src/rezplugins/build_system/custom.py:33, :107-237
"pre-built packages" schema comment       -> src/rez/package_maker.py:86
prebuilt example package                  -> example_packages/hello_world/package.py:24
prebuilt example build script             -> example_packages/hello_world/build.py:34-58
download facility (urlretrieve/urlopen)   -> ABSENT (grep -rn "urlretrieve\|urlopen\|requests\." src/rez/ src/rezplugins/)
checksum / sha256 / verify                -> ABSENT (grep -rn "sha256\|md5\|checksum\|hashlib" src/rez/ src/rezplugins/)
@include .sha1 sidecar = cache key only   -> src/rezplugins/build_process/local.py:325-332 (written)
                                             src/rez/utils/sourcecode.py:339-344, :357-365 (read as cache key)
artifact provenance (source_url, license) -> ABSENT (grep -rni "provenance\|source_url\|license" package_resources.py
                                             package_maker.py package_serialise.py)
release provenance (revision, changelog)  -> src/rez/package_resources.py:32-39, :165-170
ad-hoc provenance (rez pip)               -> src/rez/pip.py:438-440 (via catch-all src/rez/package_resources.py:173)
SOURCE_DATE_EPOCH / reproducible builds   -> ABSENT (grep -rni "SOURCE_DATE_EPOCH\|deterministic\|reproducible" src/ docs/)
solve determinism (not build determinism) -> src/rez/solver.py:57, :753, :1462
```
