# Deploy Mode Refactoring - Epic

## Overview

Improve the `etcd_action` system to provide a safe, idempotent `deploy` action while maintaining backward compatibility for third-party integrations like Kubespray.

**Status:** Planning  
**Priority:** High  
**Complexity:** High (affects core cluster management logic)

## Critical Constraint: Role Reusability

**These roles are consumed as libraries by third-party projects (e.g., Kubespray for Kubernetes).**

Third-party projects import roles, not playbooks:
```yaml
# In Kubespray's playbook
- import_role:
    name: etcd3/cluster
  vars:
    etcd_action: create  # They control via variables
```

**Therefore:**
- ✅ **MUST keep routing logic in roles** (not just playbooks)
- ✅ **MUST keep `etcd_action` variable** (consumers depend on it)
- ✅ **MUST support explicit actions** (`create`, `upgrade`) for consumers who want control
- ✅ **CAN add convenience playbooks** as wrappers for standalone users

## Design Decision: Idempotent Deploy Action

**Question:** Is a single idempotent `deploy` action worth the complexity?

**Answer:** YES - it provides significant value similar to Terraform's `apply` or Kubernetes' `apply`:

**Without idempotent deploy (current state):**
```bash
# User must choose correct action
ansible-playbook etcd.yaml -e etcd_action=create  # First time
ansible-playbook etcd.yaml -e etcd_action=upgrade # Later

# CI/CD must track state
if cluster_exists; then
  ansible-playbook etcd.yaml -e etcd_action=upgrade
else
  ansible-playbook etcd.yaml -e etcd_action=create
fi
```

**With idempotent deploy:**
```bash
# Always safe to run
ansible-playbook etcd.yaml -e etcd_action=deploy  # First time
ansible-playbook etcd.yaml -e etcd_action=deploy  # Re-run → no-op
ansible-playbook etcd.yaml -e etcd_action=deploy  # After version bump → upgrade

# CI/CD is simple
ansible-playbook etcd.yaml -e etcd_action=deploy  # Always works
```

**Value proposition:**
- ✅ **Idempotent**: Safe to re-run (like Terraform apply)
- ✅ **Simple**: One command for everything
- ✅ **Smart**: Detects state and does right thing
- ✅ **Safe**: Won't accidentally recreate existing cluster

**Complexity is manageable:**
```yaml
# Inside role - detect state and branch
- name: Check if cluster exists
  stat: path={{ etcd_data_dir }}
  register: cluster_exists

- name: Create cluster
  include_tasks: create.yaml
  when: not cluster_exists.stat.exists

- name: Upgrade/reconfigure cluster
  include_tasks: upgrade.yaml
  when: cluster_exists.stat.exists and changes_detected
  
- name: Skip (idempotent)
  debug: msg="Cluster up to date"
  when: cluster_exists.stat.exists and not changes_detected
```

## Proposed Action Matrix

Support ALL three actions to satisfy different use cases:

| Action | Purpose | Use Case | Behavior |
|--------|---------|----------|----------|
| `create` | Explicit creation | Third-party integrations (Kubespray) | Fails if cluster exists |
| `upgrade` | Explicit upgrade | Third-party integrations, manual control | Fails if cluster doesn't exist |
| `deploy` | Idempotent operation | Standalone users, CI/CD, GitOps | Smart: create/upgrade/no-op based on state |

**For third-party consumers (Kubespray):**
- Use `create` or `upgrade` explicitly
- Get full control over when operations happen
- No magic behavior

**For standalone users:**
- Use `deploy` for simplicity
- Idempotent and safe
- Similar to Terraform/Kubernetes UX

**For power users:**
- All three actions available
- Choose based on needs

---

## Current Problems

1. **Not truly idempotent:** `create` fails if exists, `upgrade` fails if not exists - need to track state
2. **Unsafe serial execution:** Playbook controls serial execution, not the role (loses quorum if misconfigured)
3. **No change detection:** Can't tell if upgrade/changes needed without trying
4. **No topology validation:** Can accidentally add/remove nodes
5. **Certificate rotation unclear:** When do certs get rotated?
6. **Standalone UX is poor:** Users must manually choose `create` vs `upgrade` vs `deploy`

**Note:** `create`/`upgrade` actions are NOT a problem for third-party consumers - they want explicit control. The problem is lack of idempotent `deploy` option for standalone users.

---

## New Design

### Hybrid Approach: Roles + Playbooks

**Keep routing in roles** (for third-party consumers like Kubespray):
```yaml
# roles/etcd3/cluster/tasks/main.yaml
- import_role: name: etcd3/backups
  when: etcd_action == "backup"

- import_role: name: etcd3/cluster/install
  when: etcd_action in ['create', 'upgrade', 'deploy']
```

**Add convenience playbooks** (for standalone users):
```yaml
# playbooks/deploy-cluster.yaml - Thin wrapper
- hosts: etcd
  serial: 1
  roles:
    - role: etcd3/cluster
      vars:
        etcd_action: deploy
        deploy_option: "{{ deploy_option | default('') }}"
```

**Support three actions** (satisfy all use cases):

| Command | Use Case |
|---------|----------|
| `ansible-playbook etcd.yaml -e etcd_action=create` | Kubespray, explicit control |
| `ansible-playbook etcd.yaml -e etcd_action=upgrade` | Kubespray, explicit control |
| `ansible-playbook etcd.yaml -e etcd_action=deploy` | Standalone, idempotent |
| `ansible-playbook playbooks/deploy-cluster.yaml` | Standalone, convenient |
| `ansible-playbook playbooks/backup-cluster.yaml` | Standalone, convenient |

**Benefits:**
- ✅ Backward compatible for Kubespray (uses `etcd_action=create/upgrade`)
- ✅ Idempotent for standalone users (uses `etcd_action=deploy`)
- ✅ Convenient playbooks for common operations
- ✅ Routing stays in roles (library pattern)
- ✅ No breaking changes

### Deploy Behavior Matrix

**Three actions, same code path, different validations:**

| Scenario | `etcd_action=create` | `etcd_action=upgrade` | `etcd_action=deploy` (idempotent) |
|----------|---------------------|----------------------|-----------------------------------|
| No cluster exists | Create new cluster | Error: no cluster to upgrade | Create new cluster |
| Cluster exists, no changes | Error: cluster exists | Skip (idempotent) | Skip (idempotent) |
| Cluster exists, version change | Error: cluster exists | Backup → Upgrade serial | Backup → Upgrade serial |
| Cluster exists, config change | Error: cluster exists | Backup → Reconfigure serial | Backup → Reconfigure serial |
| Topology changed | Error: cluster exists | Error: topology changed | Error: topology changed |
| Certs expiring soon | Warning | Warning | Warning |

**Deploy options modify behavior:**

| With `deploy_option` | `force_create` | `no_upgrade` |
|----------------------|----------------|--------------|
| No cluster | Error: no cluster to force-create | Error: no cluster to check |
| Cluster exists, no changes | Error: cluster exists | Report: no changes needed |
| Cluster needs upgrade | Error: cluster exists | Error: upgrade needed to vX.Y.Z |

**Key principle:** 
- `create`/`upgrade` = explicit control (for Kubespray)
- `deploy` = idempotent smart operation (for standalone users)
- Same underlying code, different entry validations

---

## Implementation Plan

### Phase 1: Add Idempotent Deploy Logic (Medium Risk)

**Goal:** Implement smart `deploy` action that detects state and does the right thing

**Files to modify:**
- `roles/etcd3/cluster/install/tasks/0010_cluster.yaml` - Add state detection and conditional logic
- `roles/etcd3/defaults/main.yaml` - Update etcd_action valid values

**Implementation in 0010_cluster.yaml:**
```yaml
# Detect cluster state
- name: Check if cluster exists
  stat:
    path: "{{ etcd_data_dir }}"
  register: cluster_exists

# Validation: fail for explicit actions
- name: CREATE action validation
  assert:
    that: not cluster_exists.stat.exists
    fail_msg: "Cluster exists. Use etcd_action=upgrade or delete first"
  when: etcd_action == "create"

- name: UPGRADE action validation
  assert:
    that: cluster_exists.stat.exists
    fail_msg: "No cluster to upgrade. Use etcd_action=create"
  when: etcd_action == "upgrade"

# DEPLOY action: smart routing (idempotent)
- name: Set cluster operation
  set_fact:
    cluster_operation: >-
      {%- if not cluster_exists.stat.exists -%}
      create
      {%- elif changes_needed -%}
      upgrade
      {%- else -%}
      skip
      {%- endif -%}
  when: etcd_action == "deploy"

# Execute operation
- include_tasks: create-cluster.yaml
  when: etcd_action == "create" or (etcd_action == "deploy" and cluster_operation == "create")

- include_tasks: upgrade-cluster.yaml
  when: etcd_action == "upgrade" or (etcd_action == "deploy" and cluster_operation == "upgrade")

- debug: msg="Cluster up to date"
  when: etcd_action == "deploy" and cluster_operation == "skip"
```

**Benefits:**
- ✅ Keep routing in roles (third-party compatible)
- ✅ Add idempotent `deploy` action
- ✅ Maintain explicit `create`/`upgrade` for control
- ✅ No breaking changes

### Phase 2: Add Topology Detection (Medium Risk)

**Goal:** Detect if nodes were added/removed from inventory

**Implementation:**
```yaml
# Store cluster topology in etcd member list
# Compare with inventory groups[etcd_cluster_group]
# Fail if mismatch detected

- name: Get current cluster members
  command: etcdctl member list -w json
  register: current_members

- name: Compare with inventory
  assert:
    that:
      - current_member_count == inventory_member_count
    fail_msg: |
      Topology changed detected!
      Current cluster: {{ current_member_count }} nodes
      Inventory: {{ inventory_member_count }} nodes
      
      To scale cluster:
      1. Use dedicated scaling playbook: playbooks/scale-cluster.yaml
      2. Or, delete and recreate: 
         ansible-playbook -i inventory.ini etcd.yaml -e etcd_delete_cluster=true
         ansible-playbook -i inventory.ini etcd.yaml
```

**Files to create:**
- `roles/etcd3/cluster/install/tasks/topology-check.yaml`

**Files to modify:**
- `roles/etcd3/cluster/install/tasks/0010_cluster.yaml` (include topology check)

### Phase 3: Add Change Detection (Medium Risk)

**Goal:** Detect what actually needs to change (version, config, certs, etc.)

**Implementation:**
```yaml
- name: Detect required changes
  set_fact:
    changes_needed:
      version_upgrade: "{{ current_version != target_version }}"
      config_changed: "{{ config_checksum_changed }}"
      systemd_changed: "{{ systemd_checksum_changed }}"
      certs_expiring: "{{ cert_days_remaining < 90 }}"
      topology_changed: "{{ member_count_mismatch }}"
  tags:
    - detect-changes

- name: Display change detection results
  debug:
    msg: |
      Change Detection Results:
      - Version upgrade needed: {{ changes_needed.version_upgrade }}
        Current: {{ current_version }}
        Target: {{ target_version }}
      - Config changes: {{ changes_needed.config_changed }}
      - Systemd changes: {{ changes_needed.systemd_changed }}
      - Certs expiring: {{ changes_needed.certs_expiring }}
      - Topology changed: {{ changes_needed.topology_changed }}
```

**Files to create:**
- `roles/etcd3/cluster/install/tasks/detect-changes.yaml`

**Files to modify:**
- `roles/etcd3/cluster/install/tasks/0010_cluster.yaml` (call change detection)

### Phase 4: Add Deploy Logic with Conditional Behavior (High Risk)

**Goal:** Implement intelligent deploy with all options flowing through same code path

**Implementation:**
```yaml
# Main deploy logic in 0010_cluster.yaml (same file, enhanced)

# 1. Check if cluster exists
- name: Check if cluster exists
  stat:
    path: "{{ etcd_data_dir }}"
  register: cluster_exists

- name: Check cluster health if running
  command: etcdctl endpoint health ...
  register: cluster_health
  when: cluster_exists.stat.exists
  failed_when: false

# 2. Topology check (if cluster exists)
- include_tasks: topology-check.yaml
  when: cluster_exists.stat.exists

# 3. Change detection (if cluster exists)
- include_tasks: detect-changes.yaml
  when: cluster_exists.stat.exists

# 4. Conditional logic based on deploy_option
- name: Fail if force_create and cluster exists
  fail:
    msg: "Cluster exists. Use -e etcd_delete_cluster=true first"
  when:
    - deploy_option == 'force_create'
    - cluster_exists.stat.exists

- name: Fail if no_upgrade and cluster doesn't exist
  fail:
    msg: "No cluster to check. Use etcd_action=deploy without deploy_option to create"
  when:
    - deploy_option == 'no_upgrade'
    - not cluster_exists.stat.exists

- name: Report changes (no_upgrade mode)
  debug:
    msg: "Changes detected: {{ changes_needed }}"
  when:
    - deploy_option == 'no_upgrade'
    - cluster_exists.stat.exists

- name: Fail if upgrade needed in no_upgrade mode
  fail:
    msg: "Upgrade needed to {{ etcd_version }}"
  when:
    - deploy_option == 'no_upgrade'
    - changes_needed.version_upgrade | default(false)

# 5. Create backup if changes needed (all modes except no_upgrade)
- include_role:
    name: etcd3/backups
  when:
    - cluster_exists.stat.exists
    - changes_needed | select | list | length > 0
    - deploy_option != 'no_upgrade'

# 6. Apply changes (default deploy mode)
- name: Create new cluster
  include_tasks: create-cluster-tasks.yaml
  when:
    - not cluster_exists.stat.exists
    - deploy_option != 'force_create' or not cluster_exists.stat.exists

- name: Apply changes to existing cluster
  include_tasks: apply-changes-serial.yaml
  when:
    - cluster_exists.stat.exists
    - changes_needed | select | list | length > 0
    - deploy_option != 'no_upgrade'

# 7. Skip if no changes (idempotent)
- debug:
    msg: "No changes needed, cluster is up to date"
  when:
    - cluster_exists.stat.exists
    - changes_needed | select | list | length == 0
    - deploy_option == ''
```

**Files to create:**
- `roles/etcd3/cluster/install/tasks/topology-check.yaml`
- `roles/etcd3/cluster/install/tasks/detect-changes.yaml`
- `roles/etcd3/cluster/install/tasks/apply-changes-serial.yaml`

**Files to modify:**
- `roles/etcd3/cluster/install/tasks/0010_cluster.yaml` (add conditional logic)

**Key Principle:** All code flows through the SAME tasks, with conditionals checking `deploy_option` to fail/skip/warn at appropriate points.

### Phase 5: Enforce Serial Execution in Role (Critical!)

**Goal:** Move serial execution control from playbook to role

**Current problem:**
```yaml
# playbooks/upgrade-cluster.yaml
- hosts: etcd
  serial: 1  # ← THIS IS WRONG! Playbook controls safety
```

**New approach:**
```yaml
# Inside role/etcd3/cluster/install/tasks/deploy-existing.yaml

- name: Apply changes serially (NEVER lose quorum)
  block:
    - name: Get first node
      set_fact:
        target_node: "{{ groups[etcd_cluster_group][0] }}"
    
    - name: Apply changes to first node
      include_tasks: apply-changes-single-node.yaml
      vars:
        node: "{{ target_node }}"
    
    - name: Wait for node to rejoin cluster
      command: etcdctl endpoint health --endpoints={{ target_node }}:2379
      retries: 20
      delay: 5
    
    - name: Check cluster has quorum
      command: etcdctl endpoint status
      register: quorum_check
      failed_when: quorum_check.stdout | from_json | selectattr('Status.leader', 'defined') | list | length == 0
    
    # Repeat for remaining nodes...
  when: changes_needed | select | list | length > 0
  delegate_to: localhost
  run_once: true
```

**Files to create:**
- `roles/etcd3/cluster/install/tasks/apply-changes-serial.yaml`
- `roles/etcd3/cluster/install/tasks/apply-changes-single-node.yaml`

**Files to modify:**
- `playbooks/upgrade-cluster.yaml` (remove `serial: 1`)
- `etcd.yaml` (remove serial handling)

### Phase 6: Idempotency Checks (Medium Risk)

**Goal:** Make deploy truly idempotent - safe to run multiple times

**Implementation:**
```yaml
# Before any change
- name: Calculate configuration checksums
  set_fact:
    config_checksums:
      current_etcd_conf: "{{ lookup('file', etcd_config_dir + '/' + etcd_name + '-conf.yaml') | hash('sha256') }}"
      target_etcd_conf: "{{ lookup('template', 'etcd-conf.yaml.j2') | hash('sha256') }}"
      current_systemd: "{{ lookup('file', '/etc/systemd/system/' + etcd_name + '.service') | hash('sha256') }}"
      target_systemd: "{{ lookup('template', 'etcd-host.service.j2') | hash('sha256') }}"

- name: Skip if no changes needed
  debug:
    msg: "Configuration unchanged, skipping update"
  when: config_checksums.current_etcd_conf == config_checksums.target_etcd_conf

# Only restart if something actually changed
- name: Restart etcd
  systemd:
    name: "{{ etcd_name }}"
    state: restarted
  when:
    - config_checksums.current_etcd_conf != config_checksums.target_etcd_conf or
      config_checksums.current_systemd != config_checksums.target_systemd or
      etcd_version_changed
```

### Phase 7: Mandatory Backup Before Changes (Critical!)

**Goal:** Never modify running cluster without backup

**Implementation:**
```yaml
# At start of deploy-existing.yaml
- name: Backup cluster before any changes
  include_role:
    name: etcd3/backups
  vars:
    etcd_backup_offline: false  # Online backup if cluster healthy
  when:
    - changes_needed | select | list | length > 0
    - inventory_hostname == groups[etcd_cluster_group][0]
  tags:
    - pre-deploy-backup

- name: Verify backup succeeded
  assert:
    that:
      - backup_result is succeeded
    fail_msg: "Backup failed! Aborting deploy to prevent data loss."
```

---

## Certificate Rotation Strategy

**Principle:** Certificates are NEVER auto-rotated during deploy unless explicitly requested.

### Check Certificate Status
```bash
ansible-playbook -i inventory.ini etcd.yaml -e deploy_option=no_upgrade
# Output:
# ⚠️  WARNING: Certificates expire in 45 days
# To rotate: ansible-playbook -i inventory.ini playbooks/rotate-certs.yaml
```

### Explicit Certificate Rotation
```bash
# Dedicated playbook for cert rotation
ansible-playbook -i inventory.ini playbooks/rotate-certs.yaml

# Or via deploy with flag
ansible-playbook -i inventory.ini etcd.yaml -e rotate_certs=true
```

**Implementation:**
- Create `playbooks/rotate-certs.yaml`
- Add `rotate_certs` variable (default: false)
- Only renew certs if `rotate_certs=true` OR cert expires in < 30 days

---

## Migration Path

### No Breaking Changes (Backward Compatible)

**All existing commands CONTINUE to work:**
```bash
# Third-party projects (Kubespray) - unchanged
ansible-playbook etcd.yaml -e etcd_action=create
ansible-playbook etcd.yaml -e etcd_action=upgrade
ansible-playbook etcd.yaml -e etcd_action=backup

# New idempotent action added
ansible-playbook etcd.yaml -e etcd_action=deploy  # NEW!
```

**New convenience playbooks (optional):**
```bash
# Standalone users can use convenience playbooks
ansible-playbook playbooks/deploy-cluster.yaml     # Calls etcd_action=deploy
ansible-playbook playbooks/backup-cluster.yaml     # Calls etcd_action=backup
ansible-playbook playbooks/delete-cluster.yaml     # Calls etcd_delete_cluster=true
```

### Migration Strategy

**Step 1: Add idempotent deploy logic**
- Enhance `roles/etcd3/cluster/install/tasks/0010_cluster.yaml`
- Add state detection and smart routing
- Support `etcd_action=deploy` as new idempotent option
- Keep `create` and `upgrade` working exactly as before

**Step 2: Create convenience playbooks**
- Create `playbooks/deploy-cluster.yaml` (wrapper around etcd_action=deploy)
- Create `playbooks/backup-cluster.yaml` (wrapper around etcd_action=backup)
- Create `playbooks/delete-cluster.yaml` (wrapper around etcd_delete_cluster=true)
- These are thin wrappers for user convenience

**Step 3: Update documentation**
- Document three usage patterns:
  1. **Library usage** (Kubespray): `import_role` with `etcd_action`
  2. **Explicit control**: `etcd.yaml -e etcd_action=create/upgrade`
  3. **Idempotent/simple**: `playbooks/deploy-cluster.yaml` or `etcd_action=deploy`
- Show when to use each pattern

**Step 4: Announce additions (not deprecations)**
- New `deploy` action available
- New convenience playbooks available
- Old commands still work (no migration needed)

---

## Testing Plan

### Test Scenarios

1. **New cluster creation**
   ```bash
   ansible-playbook -i inventory.ini playbooks/deploy-cluster.yaml
   # Should: Create new cluster
   ```

2. **Idempotent re-run**
   ```bash
   ansible-playbook -i inventory.ini playbooks/deploy-cluster.yaml
   ansible-playbook -i inventory.ini playbooks/deploy-cluster.yaml  # Second time
   # Should: Do nothing, report "no changes needed"
   ```

3. **Version upgrade**
   ```bash
   # Edit defaults: etcd_version: v3.5.26
   ansible-playbook -i inventory.ini playbooks/deploy-cluster.yaml
   # Should: Backup → Upgrade serially → Verify
   ```

4. **Config change (systemd tuning)**
   ```bash
   # Edit inventory: etcd_systemd_nice_level: -5
   ansible-playbook -i inventory.ini playbooks/deploy-cluster.yaml
   # Should: Backup → Reload serially → Verify
   ```

5. **Check mode (no changes)**
   ```bash
   ansible-playbook -i inventory.ini playbooks/deploy-cluster.yaml -e deploy_option=no_upgrade
   # Should: Report what would change, don't apply
   ```

6. **Topology change (should fail)**
   ```bash
   # Add etcd-4 to inventory
   ansible-playbook -i inventory.ini playbooks/deploy-cluster.yaml
   # Should: Error - topology changed, use scale-cluster.yaml
   ```

7. **Force create on existing (should fail)**
   ```bash
   ansible-playbook -i inventory.ini playbooks/deploy-cluster.yaml -e deploy_option=force_create
   # Should: Error - cluster exists, delete first
   ```

8. **Create backup**
   ```bash
   ansible-playbook -i inventory.ini playbooks/backup-cluster.yaml
   # Should: Create snapshot, upload to S3
   ```

9. **Delete cluster**
   ```bash
   ansible-playbook -i inventory.ini playbooks/delete-cluster.yaml
   # Should: Prompt for confirmation, delete everything
   ```

### Automated Testing

Create Molecule test scenarios:
- `test-new-cluster.yaml`
- `test-idempotent.yaml`
- `test-upgrade.yaml`
- `test-config-change.yaml`
- `test-topology-fail.yaml`

---

## Documentation Updates

### Files to Update

1. **README.md**
   - Replace "Cluster Management" section
   - Update all examples to use new playbook commands
   - Add "Dedicated Playbooks" section

2. **docs/operations/upgrade.md**
   - Rename to "Deploy Mode" guide
   - Show playbooks/deploy-cluster.yaml usage
   - Show check mode with deploy_option=no_upgrade

3. **playbooks/upgrade-cluster.yaml**
   - Keep as convenient wrapper around deploy-cluster.yaml
   - Or convert to symlink

4. **etcd.yaml**
   - Convert to deprecation warning playbook
   - Show migration commands

5. **improve_todo.md**
   - Mark this epic as completed

### New Documentation

Create `docs/operations/deploy-mode.md`:
- Explain single deploy command
- Show all scenarios with examples
- Flowchart of deploy decision logic

---

## Rollout Strategy

### Stage 1: Internal Testing (2 weeks)
- Implement Phases 1-3
- Test on development clusters
- Get feedback from maintainers

### Stage 2: Beta Release (4 weeks)
- Implement Phases 4-7
- Document migration guide
- Deprecation warnings for old syntax
- Call for beta testers

### Stage 3: Stable Release (2 weeks)
- Fix issues from beta
- Complete documentation
- Announce new recommended way

### Stage 4: Old Syntax Removal (9 months)
- Remove `etcd_action` variable
- Remove compatibility shims
- Update all examples

---

## Success Metrics

**Goals:**
- ✅ 100% idempotent - running deploy twice is safe
- ✅ 0 quorum loss incidents - serial execution enforced
- ✅ 100% backup before changes - never lose data
- ✅ Clear error messages - users know exactly what's wrong
- ✅ 50% reduction in GitHub issues about "when to use create vs upgrade"

**Measures:**
- Test coverage: 80%+ for deploy logic
- Documentation examples updated: 100%
- User confusion issues closed: target 10+ issues
- Breaking changes to users: 0 (deprecation path provided)

---

## Open Questions

1. **Should `deploy_option=no_upgrade` be renamed to `check` or `dry_run`?**
   - Pro: More intuitive
   - Con: Ansible has `--check` mode (conflicts?)

2. **How to handle partial failures in serial execution?**
   - Current: Stop on first failure
   - Alternative: Continue but track failed nodes?

3. **Should topology changes be allowed with explicit flag?**
   - e.g., `-e allow_topology_change=true`
   - Or always require dedicated scale playbook?

4. **Certificate rotation threshold?**
   - Warn at 90 days?
   - Error at 30 days?
   - Auto-rotate at 7 days?

---

## Related Issues

- #XX - Upgrade safety improvements
- #XX - Idempotency issues
- #XX - Quorum loss during upgrades
- #XX - Confusing create vs upgrade
- improve_todo.md - Item #15 (Ansible Best Practices)
- improve_todo.md - Item #19 (Cluster Scaling Support)

---

## Playbook Implementations

### playbooks/deploy-cluster.yaml
```yaml
---
# Smart deploy: creates new cluster, upgrades existing, or does nothing if up-to-date
# Usage: 
#   ansible-playbook -i inventory.ini playbooks/deploy-cluster.yaml
#   ansible-playbook -i inventory.ini playbooks/deploy-cluster.yaml -e deploy_option=no_upgrade
#   ansible-playbook -i inventory.ini playbooks/deploy-cluster.yaml -e deploy_option=force_create

- name: Deploy etcd cluster
  hosts: etcd
  serial: 1  # Critical: One node at a time for safe upgrades
  gather_facts: yes
  vars:
    deploy_option: "{{ deploy_option | default('') }}"
  roles:
    - role: etcd3/cluster/install
      tags:
        - deploy
        - etcd
```

### playbooks/backup-cluster.yaml
```yaml
---
# Create etcd cluster backup
# Usage: ansible-playbook -i inventory.ini playbooks/backup-cluster.yaml

- name: Backup etcd cluster
  hosts: etcd[0]
  gather_facts: yes
  roles:
    - role: etcd3/backups
      tags:
        - backup
```

### playbooks/delete-cluster.yaml
```yaml
---
# Delete etcd cluster
# Usage: ansible-playbook -i inventory.ini playbooks/delete-cluster.yaml

- name: Delete etcd cluster
  hosts: etcd
  gather_facts: yes
  roles:
    - role: etcd3/cluster/delete
      tags:
        - delete
  vars:
    etcd_delete_cluster: true
```

### Updated etcd.yaml (Deprecation Warning)
```yaml
---
# DEPRECATED: Use dedicated playbooks instead
# 
# Old: ansible-playbook etcd.yaml -e etcd_action=deploy
# New: ansible-playbook playbooks/deploy-cluster.yaml
#
# This file will be removed in a future version.

- name: Deprecation warning
  hosts: localhost
  gather_facts: no
  tasks:
    - name: Show deprecation message
      fail:
        msg: |
          ❌ DEPRECATED: etcd.yaml with etcd_action is deprecated!
          
          Please use dedicated playbooks:
          
          Deploy/upgrade:   playbooks/deploy-cluster.yaml
          Backup:           playbooks/backup-cluster.yaml
          Delete:           playbooks/delete-cluster.yaml
          
          Examples:
            ansible-playbook -i inventory.ini playbooks/deploy-cluster.yaml
            ansible-playbook -i inventory.ini playbooks/deploy-cluster.yaml -e deploy_option=no_upgrade
            ansible-playbook -i inventory.ini playbooks/backup-cluster.yaml
          
          See README.md for migration guide.
      when: etcd_action is defined

    - name: If no etcd_action, suggest playbooks
      debug:
        msg: |
          ℹ️  This playbook is deprecated. Use dedicated playbooks:
          
            playbooks/deploy-cluster.yaml  - Deploy/upgrade cluster
            playbooks/backup-cluster.yaml  - Create backup
            playbooks/delete-cluster.yaml  - Delete cluster
      when: etcd_action is not defined
```

## Implementation Checklist

### Phase 1: Add Idempotent Deploy
- [ ] Add state detection in 0010_cluster.yaml (check if cluster exists)
- [ ] Add change detection (version, config, systemd)
- [ ] Implement smart routing for `etcd_action=deploy`
- [ ] Keep validation for `create` (fail if exists)
- [ ] Keep validation for `upgrade` (fail if not exists)
- [ ] Add `deploy_option` variable to defaults (default: "")
- [ ] Test all three actions (create, upgrade, deploy)
- [ ] Test idempotency (deploy twice = no-op)

### Phase 1b: Add Convenience Playbooks (Optional)
- [ ] Create `playbooks/deploy-cluster.yaml` (wrapper calling etcd_action=deploy)
- [ ] Create `playbooks/backup-cluster.yaml` (wrapper calling etcd_action=backup)
- [ ] Create `playbooks/delete-cluster.yaml` (wrapper calling etcd_delete_cluster=true)
- [ ] Test playbooks call roles correctly

### Phase 2: Topology Detection
- [ ] Create `topology-check.yaml` task file
- [ ] Get current cluster members
- [ ] Compare with inventory
- [ ] Add helpful error messages
- [ ] Test with 3, 5, 7 node clusters

### Phase 3: Change Detection
- [ ] Create `detect-changes.yaml` task file
- [ ] Detect version changes
- [ ] Detect config changes (checksums)
- [ ] Detect systemd changes
- [ ] Detect cert expiration
- [ ] Set `changes_needed` fact
- [ ] Test all change types

### Phase 4: Deploy Logic
- [ ] Create `deploy-new.yaml` (new cluster)
- [ ] Create `deploy-existing.yaml` (existing cluster)
- [ ] Create `deploy-no-upgrade.yaml` (check mode)
- [ ] Route in main.yml based on deploy_mode
- [ ] Implement deploy decision matrix
- [ ] Add comprehensive error messages
- [ ] Test all scenarios

### Phase 5: Serial Execution
- [ ] Create `apply-changes-serial.yaml`
- [ ] Create `apply-changes-single-node.yaml`
- [ ] Enforce serial in role (not playbook)
- [ ] Add quorum checks between nodes
- [ ] Add health checks between nodes
- [ ] Remove `serial: 1` from playbooks
- [ ] Test with simulated node failures

### Phase 6: Idempotency
- [ ] Add checksum calculations
- [ ] Skip unchanged tasks
- [ ] Add "no changes" reporting
- [ ] Test multiple runs without changes
- [ ] Test multiple runs with changes

### Phase 7: Mandatory Backup
- [ ] Add pre-deploy backup task
- [ ] Verify backup success
- [ ] Fail deploy if backup fails
- [ ] Skip backup if no changes
- [ ] Test backup failures

### Testing
- [ ] Create Molecule test scenarios
- [ ] Test new cluster creation
- [ ] Test idempotent re-runs
- [ ] Test version upgrades
- [ ] Test config changes
- [ ] Test topology change failures
- [ ] Test force_create failures
- [ ] Test no_upgrade check mode

### Documentation
- [ ] Update README.md
- [ ] Update upgrade documentation
- [ ] Create deploy-mode.md guide
- [ ] Update all examples
- [ ] Create migration guide
- [ ] Update changelog

### Release
- [ ] Beta release with deprecation warnings
- [ ] Gather feedback
- [ ] Fix issues
- [ ] Stable release
- [ ] Announce new recommended way
- [ ] Schedule old syntax removal

---

## Timeline Estimate

- **Phase 1-2:** 1 week (low risk refactoring)
- **Phase 3-4:** 2 weeks (core logic)
- **Phase 5:** 1 week (serial execution - critical)
- **Phase 6-7:** 1 week (safety features)
- **Testing:** 1 week (comprehensive testing)
- **Documentation:** 1 week (complete rewrite)
- **Beta period:** 4 weeks (gather feedback)
- **Fixes & stable:** 1 week (polish)

**Total:** ~12 weeks (3 months) to stable release

---

## Notes

### Why This Design?

**Problem:** Two different user types with different needs:
1. **Third-party consumers** (Kubespray): Want explicit control via `create`/`upgrade`
2. **Standalone users**: Want idempotent simplicity like Terraform apply

**Solution:** Support both patterns:
- Keep explicit `create`/`upgrade` actions (no breaking changes)
- Add idempotent `deploy` action (new capability)
- Routing stays in roles (library pattern)
- Optional convenience playbooks (user experience)

**Complexity trade-off:**
- ✅ More complex internally (state detection, smart routing)
- ✅ Much simpler externally (idempotent `deploy` just works)
- ✅ Similar to Terraform apply, Kubernetes apply, Ansible `state: present`

**Backward compatibility:**
- ✅ Kubespray continues using `etcd_action=create/upgrade`
- ✅ No breaking changes to existing integrations
- ✅ New idempotent option for those who want it

**Payoff:**
- **Idempotent**: Safe to re-run (like Terraform apply)
- **Smart**: Detects state automatically
- **Flexible**: Choose explicit or idempotent based on needs
- **Compatible**: Works as library or standalone
- **Safe**: Enforced serial execution, mandatory backups
- **Better UX**: Clear error messages, check mode

The complexity is moved from the user (tracking state, choosing create vs upgrade) to the code (intelligent detection), which is exactly where it should be.
