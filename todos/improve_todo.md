# Etcd-Ansible Improvement TODO

## Status Legend
- ✅ COMPLETED
- 🚧 IN PROGRESS
- 📋 APPROVED - Ready to implement
- ⏳ TODO LATER - Deferred
- ❌ WON'T FIX

## High Priority Issues

### 1. Add `etcdutl` for Snapshot Verification (etcd v3.6+) ✅ COMPLETED
**Motivation**: etcd v3.6+ requires `etcdutl` for snapshot status checks instead of `etcdctl`.
**Impact**: Backup verification may fail or use deprecated commands on newer etcd versions.
**Status**: COMPLETED
**What was done**:
- [x] Updated `roles/etcd3/backups/tasks/main.yaml` to use `etcdutl snapshot status`
- [x] Cron backup scripts already use etcdutl (verified)
- [x] Added snapshot verification after each backup (both online and offline)
- [x] Verification failures now fail the backup task to prevent uploading corrupted snapshots

### 2. Missing Test Infrastructure ❌ WON'T FIX
**Motivation**: No automated testing exists (make test fails).
**Impact**: Changes can't be validated automatically, increasing risk of regressions.
**Status**: WON'T FIX - Test infrastructure would require significant effort
**Rationale**: Manual testing with test-etcd.yaml and existing Makefile targets provide adequate validation for this project's scope

### 3. Inconsistent Error Handling ✅ COMPLETED
**Motivation**: Mixed use of `ignore_errors`, `failed_when`, and proper error handling.
**Impact**: Failures may be silently ignored or cause unexpected behavior.
**Status**: COMPLETED - Error handling improved throughout
**What was done**:
- [x] Audit all tasks for error handling patterns
- [x] Standardize on `failed_when` with explicit conditions
- [x] Add proper rescue/always blocks for critical operations
- [x] Add validation tasks before destructive operations

### 4. Certificate Expiration Monitoring ⏳ TODO LATER
**Motivation**: No automated check for certificate expiration.
**Impact**: Certificates can expire unexpectedly, causing cluster outages.
**Status**: TODO LATER - Smallstep CA handles automatic renewal
**Note**: Smallstep automatically renews at 2/3 lifetime (~487 days for 2-year certs). Health check playbook will include certificate status.

### 5. Backup Retention Policy ✅ COMPLETED
**Motivation**: Backups accumulate indefinitely with no cleanup.
**Impact**: Disk space exhaustion on backup storage.
**Status**: COMPLETED - Managed by S3 lifecycle policies
**Implementation**:
- ✅ Backup files include datetime in path (YYYY/MM/filename-YYYY-MM-DD_HH-MM-SS)
- ✅ S3 lifecycle policies manage retention automatically
- ✅ `etcd_backup_retention_days` and `ca_backup_retention_days` variables exist for local cleanup
- ✅ Cron scripts include retention cleanup logic

## Medium Priority Issues

### 6. Hard-coded Binary Paths ✅ COMPLETED
**Motivation**: Paths like `/opt/bin` are hard-coded throughout.
**Impact**: Difficult to customize for different environments.
**Status**: COMPLETED - All paths use `{{ bin_dir }}` variable
**Note**: All templates and tasks verified to use bin_dir variable consistently

### 7. Complex Jinja2 Templates in Facts Role ⏳ TODO LATER
**Motivation**: `roles/etcd3/facts/tasks/main.yaml` has very complex Jinja2.
**Impact**: Difficult to understand, debug, and maintain.
**Status**: TODO LATER - Works correctly, refactoring deferred
**Note**: Current implementation is functional; will refactor when time permits

### 8. No Health Check Playbook ✅ COMPLETED
**Motivation**: No dedicated playbook to verify cluster health.
**Impact**: Operators must manually check cluster status.
**Status**: COMPLETED
**What was done**:
- [x] Created `playbooks/etcd-health.yaml`
- [x] Checks all endpoints with `etcdctl endpoint health`
- [x] Verifies cluster member list and endpoint status
- [x] Checks certificate expiration (peer, server, client) with warning thresholds
- [x] Displays cluster metrics (database size with quota warnings)
- [x] Checks step-ca health on cert-managers
- [x] Checks renewal timer status
- [x] Supports JSON output for monitoring integration
- [x] Provides actionable recommendations for issues
- [x] Supports tags for selective checks

### 9. Secrets Management Best Practices ✅ COMPLETED
**Motivation**: Variables show plaintext credentials without Vault examples.
**Impact**: Risk of credential exposure in version control.
**Status**: COMPLETED
**What was done**:
- [x] Replace GPG with AWS KMS for CA backup encryption (playbooks/backup-ca.yaml)
- [x] Add symmetric encryption option with ansible-vault (step_ca_backup_encryption_method)
- [x] Document backup encryption best practices (CERTIFICATE_ARCHITECTURE.md)
- [x] Add restore playbook with encrypted backup support (playbooks/restore-ca-from-backup.yaml)
- [x] Add vault.yml.example with comprehensive documentation
- [x] Add KMS setup playbook (playbooks/setup-kms.yaml)
- [x] Add `.gitignore` patterns for secret files (vault.yml, .vault-pass, credentials, etc.)
- [x] Document .gitignore in README.md with security warnings

### 10. Download Role Complexity ✅ COMPLETED
**Motivation**: `roles/download_etcd/` had complex container logic.
**Impact**: Difficult to maintain, Docker-only support.
**Status**: COMPLETED - Simplified to etcd3/download
**What was done**:
- [x] Simplified download role to only handle file downloads
- [x] Moved to `etcd3/download` role hierarchy for better organization
- [x] Removed all container/Docker logic (download_container.yml, sync_container.yml, etc.)
- [x] Removed unnecessary variables (download_run_once, download_localhost, etc.)
- [x] Standardized checksum verification using get_url's built-in checksum parameter
- [x] Reduced from ~400 lines across 6 files to ~60 lines in 3 files

### 11. Systemd Service Customization ✅ COMPLETED
**Motivation**: Service template has hard-coded values.
**Impact**: Cannot customize for different environments (ionice, nice, etc.).
**Status**: COMPLETED
**What was done**:
- [x] Added variables for systemd service customization:
  - `etcd_systemd_timeout_start_sec` (default: 60s)
  - `etcd_systemd_restart_sec` (default: 15s)
  - `etcd_systemd_limit_nofile` (default: 40000)
  - `etcd_systemd_nice_level` (optional)
  - `etcd_systemd_ionice_class` (optional)
  - `etcd_systemd_ionice_priority` (optional)
  - `etcd_systemd_memory_limit` (optional)
  - `etcd_systemd_cpu_quota` (optional)
- [x] Updated etcd-host.service.j2 template
- [x] All variables defined in roles/etcd3/defaults/main.yaml
- [x] Optional tuning variables only applied when defined

### 12. Upgrade Safety Checks ✅ COMPLETED
**Motivation**: Upgrades can be destructive without proper validation.
**Impact**: Risk of cluster downtime or data loss during upgrades.
**Status**: COMPLETED
**What was done**:
- [x] Added disk space validation (minimum 10GB free)
- [x] Added version compatibility check (prevents downgrades)
- [x] Enhanced error messages with actionable troubleshooting steps
- [x] Added health check after each node restart during upgrades
- [x] Improved task naming and logging for better visibility
- [x] Serial rollout documented (use serial=1 at play level)
- [x] Better validation messages for create vs upgrade vs deploy actions

## Medium Priority Issues

### 13. Monitoring Integration ⏳ TODO LATER
**Motivation**: No built-in monitoring/alerting integration.
**Impact**: Operators must manually set up monitoring.
**Status**: TODO LATER - Health check playbook provides basic monitoring
**Note**: Health check playbook supports JSON output for integration with monitoring systems

### 14. Multi-Version Support Matrix ⏳ TODO LATER
**Motivation**: Unclear which etcd versions are supported.
**Impact**: Users may try unsupported versions.
**Status**: TODO LATER - Document minimum versions in defaults
**Note**: Will document tested versions: v3.5.13, v3.5.26, v3.6.7

### 15. Ansible Best Practices 📋 APPROVED
**Motivation**: Some tasks don't follow Ansible best practices.
**Impact**: Reduced maintainability and readability.
**Status**: APPROVED - Implementing now
**What needs to happen**:
- [ ] Add proper `changed_when` and `failed_when` to command/shell tasks
- [ ] Use `block` for grouped tasks with rescue/always
- [ ] Add descriptive task names
- [ ] Improve error messages
- [ ] Add tags consistently

### 16. Documentation Improvements ⏳ TODO LATER
**Motivation**: Missing inline documentation and troubleshooting guides.
**Impact**: Difficult for new users to understand and debug.
**Status**: TODO LATER - Basic documentation exists
**Note**: README.md and CERTIFICATE_ARCHITECTURE.md provide comprehensive documentation

### 17. Performance Optimization ⏳ TODO LATER
**Motivation**: Serial operations could be parallelized.
**Impact**: Slower execution for large clusters.
**Status**: TODO LATER - Current performance is acceptable
**Note**: Serial upgrades are intentional for safety

### 18. IPv6 Support ⏳ TODO LATER
**Motivation**: Code assumes IPv4 addresses.
**Impact**: Cannot deploy in IPv6-only environments.
**Status**: TODO LATER - IPv4 is sufficient for current use cases

### 19. Cluster Scaling Support 📋 APPROVED
**Motivation**: No support for adding/removing cluster members.
**Impact**: Cluster size is fixed after creation.
**Status**: APPROVED - Implementing now
**What needs to happen**:
- [ ] Create `playbooks/scale-cluster.yaml` for documented scaling procedure
- [ ] Add validation for minimum cluster size (3 nodes)
- [ ] Add pre-scale health checks
- [ ] Document current behavior (--limit works for adding nodes)

### 20. Backup Verification 📋 APPROVED
**Motivation**: Backups are created but never verified.
**Impact**: Backups may be corrupted and unusable.
**Status**: APPROVED - Implementing now
**What needs to happen**:
- [ ] Add `etcdutl snapshot status` after backup in main.yaml
- [ ] Update cron backup scripts to verify snapshots
- [ ] Fail task if verification fails
- [ ] Log verification results

## Technical Debt

### 21. Remove Deprecated Features 📋 APPROVED
**Motivation**: Code contains support for deprecated etcd v2.
**Impact**: Adds complexity without value.
**Status**: APPROVED - Implementing now
**What needs to happen**:
- [ ] Verify etcd v2 is disabled (enable-v2: false already in config)
- [ ] Document minimum supported versions in defaults
- [ ] Add comments about version support
- [ ] Clean up any obsolete version conditionals

### 22. Consolidate Download Roles ✅ COMPLETED
**Motivation**: Separate download logic for etcd and certs.
**Impact**: Duplicated code and inconsistent patterns.
**Status**: COMPLETED
**What was done**:
- [x] Simplified download role to only handle file downloads
- [x] Moved to `etcd3/download` role hierarchy for better organization
- [x] Added meta dependency on etcd3 to automatically load defaults
- [x] Removed all container/Docker logic
- [x] Removed unnecessary variables
- [x] Standardized checksum verification using get_url's built-in checksum parameter
- [x] Reduced from ~400 lines across 6 files to ~60 lines in 3 files
- [x] Updated all role references from `download_etcd` to `etcd3/download`
- [x] Simplified test-download.yaml

### 23. Improve Variable Naming 📋 APPROVED
**Motivation**: Some variables have unclear names.
**Impact**: Reduced code readability.
**Status**: APPROVED - Implementing now
**What needs to happen**:
- [ ] Rename `ipvar` to `etcd_ip_variable` in facts role
- [ ] Add comments for complex variables
- [ ] Ensure consistent snake_case naming
- [ ] Add validation for critical variables

## Implementation Summary

### Approved for Implementation NOW 📋
15. **Ansible Best Practices** (#15) - Add changed_when, failed_when, better task names
19. **Cluster Scaling Support** (#19) - Create playbooks/scale-cluster.yaml
20. **Backup Verification** (#20) - Add etcdutl verification to backups
21. **Remove Deprecated Features** (#21) - Document version support
23. **Improve Variable Naming** (#23) - Rename ipvar, add comments

### Completed ✅
1. **Add etcdutl for Snapshot Verification** - Verification added to all backup tasks (commit d9f686f)
3. **Inconsistent Error Handling** - Error handling improved throughout
5. **Backup Retention Policy** - S3 lifecycle + datetime in filenames
6. **Hard-coded Binary Paths** - All use {{ bin_dir }} variable
8. **No Health Check Playbook** - Comprehensive health check with JSON output (commit b5b143f)
9. **Secrets Management Best Practices** - AWS KMS encryption, .gitignore, vault.yml.example (commit f104428)
10. **Download Role Complexity** - Simplified to etcd3/download
11. **Systemd Service Customization** - Tuning variables for timeout, limits, nice, ionice, memory, CPU (commit c852aa3)
12. **Upgrade Safety Checks** - Disk space, version validation, better error messages
22. **Consolidate Download Roles** - Completed simplification
**User/Group Consolidation** - Removed etcd_cert_user/group, use etcd_user.name (commits 56ff6f3, 8795e8b)

### Deferred ⏳
4. **Certificate Expiration Monitoring** - Smallstep handles auto-renewal
7. **Complex Jinja2 Templates** - Works correctly, refactor later
13. **Monitoring Integration** - Health check provides basic functionality
14. **Multi-Version Support Matrix** - Document later
16. **Documentation Improvements** - Adequate documentation exists
17. **Performance Optimization** - Current performance acceptable
18. **IPv6 Support** - Not needed for current use cases

### Won't Fix ❌
2. **Missing Test Infrastructure** - Manual testing sufficient

## Next Steps

### Phase 1: Immediate Improvements (This Sprint)
1. Add .gitignore for secrets
2. Add etcdutl snapshot verification to backups
3. Create playbooks/etcd-health.yaml
4. Add systemd service customization variables
5. Improve error messages and validation

### Phase 2: Code Quality (Next Sprint)
6. Rename ipvar to etcd_ip_variable
7. Add changed_when/failed_when consistently
8. Create playbooks/scale-cluster.yaml
9. Document minimum supported versions
10. Enhance vault.yml.example

### Phase 3: Optional Enhancements (Future)
- Jinja2 template refactoring
- Monitoring integration
- IPv6 support
- Performance optimization
