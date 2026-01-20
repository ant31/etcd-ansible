# Etcd-Ansible Improvement TODO

## High Priority Issues

### 1. Add `etcdutl` for Snapshot Verification (etcd v3.6+)
**Motivation**: etcd v3.6+ requires `etcdutl` for snapshot status checks instead of `etcdctl`.
**Impact**: Backup verification may fail or use deprecated commands on newer etcd versions.
**What needs to happen**:
- [ ] Update `roles/etcd3/backups/tasks/main.yaml` to use `etcdutl snapshot status` instead of `etcdctl snapshot status`
- [ ] Add version-aware conditional to support both old and new methods
- [ ] Update snapshot verification in restore TODO

### 2. Missing Test Infrastructure
**Motivation**: No automated testing exists (make test fails).
**Impact**: Changes can't be validated automatically, increasing risk of regressions.
**What needs to happen**:
- [ ] Add Makefile with test target
- [ ] Implement molecule tests for roles
- [ ] Add integration tests for common scenarios (install, upgrade, backup, restore)
- [ ] Add CI/CD pipeline configuration (.github/workflows or .gitlab-ci.yml)
- [ ] Create test inventory files with different cluster sizes

### 3. Inconsistent Error Handling
**Motivation**: Mixed use of `ignore_errors`, `failed_when`, and proper error handling.
**Impact**: Failures may be silently ignored or cause unexpected behavior.
**Status**: ✅ IMPROVED
**What needs to happen**:
- [x] Audit all tasks for error handling patterns
- [x] Standardize on `failed_when` with explicit conditions
- [x] Add proper rescue/always blocks for critical operations
- [x] Document when `ignore_errors` is acceptable
- [x] Add validation tasks before destructive operations

### 4. Certificate Expiration Monitoring
**Motivation**: No automated check for certificate expiration.
**Impact**: Certificates can expire unexpectedly, causing cluster outages.
**What needs to happen**:
- [ ] Add task to check certificate expiration dates
- [ ] Create warning when certificates expire within threshold (e.g., 30 days)
- [ ] Add automated certificate rotation playbook
- [ ] Document manual rotation procedure
- [ ] Add certificate expiration to health check tasks

### 5. Backup Retention Policy
**Motivation**: Backups accumulate indefinitely with no cleanup.
**Impact**: Disk space exhaustion on backup storage.
**What needs to happen**:
- [ ] Add `etcd_backup_retention_days` variable
- [ ] Implement cleanup task to remove old backups
- [ ] Add retention policy for S3/object storage
- [ ] Document backup rotation strategy
- [ ] Add option to archive old backups before deletion

## Medium Priority Issues

### 6. Hard-coded Binary Paths
**Motivation**: Paths like `/opt/bin` are hard-coded throughout.
**Impact**: Difficult to customize for different environments.
**What needs to happen**:
- [ ] Ensure all binary paths use `{{bin_dir}}` variable
- [ ] Add validation that binaries exist before use
- [ ] Support multiple binary locations (PATH lookup)
- [ ] Document binary installation requirements

### 7. Complex Jinja2 Templates in Facts Role
**Motivation**: `roles/etcd3/facts/tasks/main.yaml` has very complex Jinja2.
**Impact**: Difficult to understand, debug, and maintain.
**What needs to happen**:
- [ ] Break down complex set_fact into multiple simpler tasks
- [ ] Add intermediate variables with descriptive names
- [ ] Add comments explaining the logic
- [ ] Consider using JSON files or lookup plugins
- [ ] Add examples of expected output

### 8. No Health Check Playbook
**Motivation**: No dedicated playbook to verify cluster health.
**Impact**: Operators must manually check cluster status.
**What needs to happen**:
- [ ] Create `playbooks/etcd-health.yaml`
- [ ] Check all endpoints with `etcdctl endpoint health`
- [ ] Verify cluster member list
- [ ] Check certificate validity
- [ ] Display cluster metrics (size, revision, etc.)
- [ ] Add option to output JSON for monitoring systems

### 9. Secrets Management Best Practices ✅ IMPROVED
**Motivation**: Variables show plaintext credentials without Vault examples.
**Impact**: Risk of credential exposure in version control.
**Status**: Partially completed - backup encryption improved
**What was done**:
- [x] Replace GPG with AWS KMS for CA backup encryption
- [x] Add symmetric encryption option with ansible-vault
- [x] Document backup encryption best practices
- [x] Add restore playbook with encrypted backup support
**What still needs to happen**:
- [ ] Add ansible-vault examples for all sensitive variables
- [ ] Add `.gitignore` patterns for secret files
- [ ] Create example vault file structure
- [ ] Document integration with external secret managers (HashiCorp Vault, etc.)

### 10. Download Role Complexity
**Motivation**: `roles/download_etcd/` has complex container logic.
**Impact**: Difficult to maintain, Docker-only support.
**What needs to happen**:
- [ ] Simplify download logic (only file downloads are used for etcd)
- [ ] Remove unnecessary container download code
- [ ] Add support for podman if container runtime needed
- [ ] Add checksum verification for all downloads
- [ ] Cache downloads to reduce external dependencies

### 11. Systemd Service Customization
**Motivation**: Service template has hard-coded values.
**Impact**: Cannot customize for different environments (ionice, nice, etc.).
**What needs to happen**:
- [ ] Add variables for systemd service customization:
  - `etcd_systemd_nice_level`
  - `etcd_systemd_ionice_class`
  - `etcd_systemd_memory_limit`
  - `etcd_systemd_cpu_limit`
- [ ] Add support for systemd drop-in files
- [ ] Document performance tuning options

### 12. Upgrade Safety Checks
**Motivation**: Upgrades can be destructive without proper validation.
**Impact**: Risk of cluster downtime or data loss during upgrades.
**What needs to happen**:
- [ ] Add pre-upgrade validation tasks:
  - Check cluster health
  - Verify backup exists
  - Check version compatibility
  - Validate free disk space
- [ ] Add option for dry-run mode
- [ ] Implement gradual rollout (one node at a time with health checks)
- [ ] Add rollback procedure documentation

## Low Priority / Nice to Have

### 13. Monitoring Integration
**Motivation**: No built-in monitoring/alerting integration.
**Impact**: Operators must manually set up monitoring.
**What needs to happen**:
- [ ] Add Prometheus metrics exporter configuration
- [ ] Create Grafana dashboard templates
- [ ] Add example alerting rules
- [ ] Document integration with monitoring systems
- [ ] Add health check endpoint for load balancers

### 14. Multi-Version Support Matrix
**Motivation**: Unclear which etcd versions are supported.
**Impact**: Users may try unsupported versions.
**What needs to happen**:
- [ ] Document supported etcd versions
- [ ] Add version compatibility checks
- [ ] Update README with version matrix
- [ ] Add deprecation warnings for old versions
- [ ] Test with multiple etcd versions

### 15. Ansible Best Practices
**Motivation**: Some tasks don't follow Ansible best practices.
**Impact**: Reduced maintainability and readability.
**What needs to happen**:
- [ ] Use `ansible-lint` and fix warnings
- [ ] Add `become` only where needed (not role-wide)
- [ ] Use FQCN (Fully Qualified Collection Names)
- [ ] Add proper tags to all tasks
- [ ] Use `block` for grouped tasks
- [ ] Add `check_mode` support where applicable

### 16. Documentation Improvements
**Motivation**: Missing inline documentation and troubleshooting guides.
**Impact**: Difficult for new users to understand and debug.
**What needs to happen**:
- [ ] Add comments to complex tasks
- [ ] Create troubleshooting guide in docs/
- [ ] Add architecture diagrams
- [ ] Document all variables with examples
- [ ] Add FAQ section
- [ ] Create upgrade guide with examples

### 17. Performance Optimization
**Motivation**: Serial operations could be parallelized.
**Impact**: Slower execution for large clusters.
**What needs to happen**:
- [ ] Identify tasks that can run in parallel
- [ ] Use `strategy: free` where appropriate
- [ ] Optimize fact gathering (gather_subset)
- [ ] Cache downloaded files properly
- [ ] Reduce unnecessary task executions with conditionals

### 18. IPv6 Support
**Motivation**: Code assumes IPv4 addresses.
**Impact**: Cannot deploy in IPv6-only environments.
**What needs to happen**:
- [ ] Add IPv6 address detection
- [ ] Update certificate generation for IPv6
- [ ] Test with IPv6-only clusters
- [ ] Update documentation with IPv6 examples
- [ ] Support dual-stack configurations

### 19. Cluster Scaling Support
**Motivation**: No support for adding/removing cluster members.
**Impact**: Cluster size is fixed after creation.
**What needs to happen**:
- [ ] Create `etcd_action: scale_up` logic
- [ ] Create `etcd_action: scale_down` logic
- [ ] Add member addition/removal tasks
- [ ] Update certificates for new members
- [ ] Document scaling procedures and limitations
- [ ] Add validation for minimum cluster size (3 nodes)

### 20. Backup Verification
**Motivation**: Backups are created but never verified.
**Impact**: Backups may be corrupted and unusable.
**What needs to happen**:
- [ ] Add `etcdutl snapshot status` after each backup
- [ ] Verify snapshot hash
- [ ] Add option to test restore in temporary directory
- [ ] Log backup verification results
- [ ] Alert on verification failures

## Technical Debt

### 21. Remove Deprecated Features
**Motivation**: Code contains support for deprecated etcd v2.
**Impact**: Adds complexity without value.
**What needs to happen**:
- [ ] Remove etcd v2 references (`enable-v2: false` is hard-coded)
- [ ] Clean up version conditionals for old versions
- [ ] Update minimum supported version to 3.4+
- [ ] Remove compatibility code for unsupported Ansible versions

### 22. Consolidate Download Roles ✅ COMPLETED
**Motivation**: Separate download logic for etcd and certs.
**Impact**: Duplicated code and inconsistent patterns.
**What was done**:
- [x] Simplified download role to only handle file downloads
- [x] Moved to `etcd3/download` role hierarchy for better organization
- [x] Added meta dependency on etcd3 to automatically load defaults
- [x] Removed all container/Docker logic (download_container.yml, sync_container.yml, etc.)
- [x] Removed unnecessary variables (download_run_once, download_localhost, download_compress, etc.)
- [x] Standardized checksum verification using get_url's built-in checksum parameter
- [x] Reduced from ~400 lines across 6 files to ~60 lines in 3 files
- [x] Maintained independent execution capability for offline/pre-staging scenarios
- [x] Updated all role references from `download_etcd` to `etcd3/download`
- [x] Simplified test-download.yaml (no manual defaults loading needed)

### 23. Improve Variable Naming
**Motivation**: Some variables have unclear names.
**Impact**: Reduced code readability.
**What needs to happen**:
- [ ] Rename ambiguous variables (e.g., `ipvar`)
- [ ] Use consistent naming conventions (snake_case)
- [ ] Group related variables with common prefixes
- [ ] Document variable purpose and expected values
- [ ] Add variable validation tasks

## Summary by Impact

### Critical (Cluster Stability/Security)
- Certificate expiration monitoring (#4)
- Upgrade safety checks (#12)
- Error handling standardization (#3)
- Secrets management (#9)

### High (Operational Excellence)
- Test infrastructure (#2)
- Backup retention (#5)
- Health check playbook (#8)
- etcdutl migration (#1)

### Medium (Maintainability)
- Jinja2 template simplification (#7)
- Documentation improvements (#16)
- Ansible best practices (#15)
- Hard-coded paths (#6)

### Low (Features/Enhancements)
- Monitoring integration (#13)
- Cluster scaling (#19)
- IPv6 support (#18)
- Performance optimization (#17)

## Quick Wins (Low Effort, High Impact)
1. Add Makefile with basic test target
2. Document certificate expiration checking
3. Add etcdutl for snapshot verification
4. Create health check playbook
5. Add ansible-lint configuration and fix warnings
6. Document backup retention strategy
