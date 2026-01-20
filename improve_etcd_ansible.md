# Etcd-Ansible Improvement Plan

This document outlines identified issues and proposed improvements for the etcd-ansible repository, focusing on reliability, security, and maintainability.

## 1. Reliability & Operations

### 1.1 Robust Rolling Upgrades
**Issue**: The current upgrade logic in `roles/etcd3/cluster/install/tasks/0010_cluster.yaml` uses a `run_once` loop with delegation to restart services. This approach checks variables (`confchanged`, etc.) against the *first* host in the batch, potentially leading to incorrect restart behavior (e.g., if config changed on node 2 but not node 1, the restart might be skipped).
**Proposal**:
- Refactor `etcd.yaml` to use `serial: 1` (or a percentage) when `etcd_action` is `upgrade`.
- Remove the complex `run_once` loop for restarts and rely on standard Ansible linear task execution per host.
- Ensure health checks run after *each* node restart before proceeding to the next node in the serial batch.
- Ensure binary updates trigger restarts (currently only config/systemd changes trigger restarts).

### 1.2 Snapshot Verification
**Issue**: While the cron backup script uses `etcdutl` to verify snapshots, the ad-hoc backup task in `roles/etcd3/backups/tasks/main.yaml` creates a snapshot but does not verify its integrity using `etcdutl snapshot status`.
**Proposal**:
- Add a task to `roles/etcd3/backups/tasks/main.yaml` to run `etcdutl snapshot status` on the generated snapshot file immediately after creation.
- Fail the backup task if verification fails to prevent uploading corrupted snapshots.

### 1.3 Python Dependency Management
**Issue**: `roles/etcd3/backups/tasks/upload_object_storage.yaml` installs `boto3` and `botocore` using `pip` module globally. On modern Linux distributions (Debian 12+, Ubuntu 24.04), this may conflict with system packages (PEP 668 managed environments).
**Proposal**:
- Prefer installing system packages (e.g., `python3-boto3`) via `apt`/`dnf` if available.
- Or, install python dependencies into a virtual environment and point Ansible to use that python interpreter for the S3 tasks.

## 2. Maintainability & Code Structure

### 2.1 Simplify Fact Generation
**Issue**: `roles/etcd3/facts/tasks/main.yaml` uses complex, nested Jinja2 templates to generate connection strings and member lists. This makes debugging difficult and increases the learning curve for new contributors.
**Proposal**:
- Create a custom Ansible filter plugin (in `plugins/filter/`) to handle the logic of generating peer URLs and member strings in Python code, which is easier to test and read than complex Jinja2 blocks.

### 2.2 Standardize Binary Paths
**Issue**: Binary paths like `/opt/bin` are sometimes hardcoded or assumed in scripts.
**Proposal**:
- Strict enforcement of `{{ bin_dir }}` usage across all templates and tasks.
- Ensure `PATH` is updated in `~/.bashrc` or `/etc/profile.d/` for the `etcd` user so manual administrative commands work easily without full paths.

## 3. Security

### 3.1 Secrets Management
**Issue**: While Vault is recommended, some defaults (like in `roles/etcd3/certs/smallstep/defaults/main.yml`) generate passwords using `lookup('password', ...)` which saves plaintext passwords to local files on the controller.
**Proposal**:
- Ensure documentation emphasizes that `lookup('password', ...)` files should be secured or gitignored.
- Provide a strict "Production Mode" variable that fails if passwords are not provided via Vault.

### 3.2 File Permissions
**Issue**: Verify `umask` or explicit modes for all created directories.
**Proposal**:
- Audit all `file`, `copy`, and `template` tasks to ensure `mode`, `owner`, and `group` are explicitly set, especially for backup directories and configuration files.

## 4. Testing

### 4.1 Automated Testing
**Issue**: Lack of CI/CD integration for PRs.
**Proposal**:
- Implement Molecule tests for individual roles.
- Create a GitHub Actions workflow that spins up a ephemeral cluster (using kind or vagrant) to run the full `etcd.yaml` playbook and verify cluster health.

## 5. Documentation

### 5.1 Version Matrix
**Issue**: It is not immediately clear which etcd versions are fully supported and tested against which OS versions.
**Proposal**:
- Add a compatibility matrix to `README.md`.
