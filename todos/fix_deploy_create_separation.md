# Separate CREATE and DEPLOY Actions - Complete TODO List

## Problem Statement

Currently `create` and `deploy` are merged together, which causes complexity in state detection.
The real mistake was merging CREATE with DEPLOY - what should have been merged is DEPLOY with UPGRADE.

## Clear Action Definitions

### CREATE (new cluster initialization)
- ✅ No backup (nothing to backup yet)
- ✅ Can cleanup/force create directories
- ✅ Start ALL nodes SIMULTANEOUSLY (parallel)
- ✅ Don't check cluster health beforehand
- ✅ Set initial-cluster-state: new
- ✅ Used for: First-time cluster creation

### DEPLOY (idempotent cluster operations)
- ✅ ALWAYS backup before changes
- ✅ Only apply needed changes
- ✅ Restart nodes ONE-BY-ONE (serial, maintains quorum)
- ✅ Check cluster health before/after
- ✅ Can involve: config changes, version upgrades, etc.
- ✅ Set initial-cluster-state: existing
- ✅ Used for: Any operation on a running cluster

### RESTORE (disaster recovery)
- ✅ Uses CREATE parallel start path
- ✅ Set initial-cluster-state: new (required by etcd)
- ✅ All nodes start together

## Files That Need Changes

### 1. roles/etcd3/defaults/main.yaml
- [ ] Change `etcd_action: deploy` to document both `create` and `deploy`
- [ ] Remove `etcd_new_cluster` variable (no longer needed)
- [ ] Update comments to clarify CREATE vs DEPLOY

### 2. roles/etcd3/cluster/install/tasks/0010_cluster.yaml (MAJOR CHANGES)
- [ ] Split logic into clear CREATE vs DEPLOY paths
- [ ] CREATE path: Skip all health checks, force cleanup if requested, parallel start
- [ ] DEPLOY path: Always backup first, serial restart, health checks
- [ ] Remove complex state detection (etcd_new_cluster, cluster query, etc.)
- [ ] Simplify: if action==create → new cluster mode, else → existing cluster mode
- [ ] RESTORE path: Use CREATE logic (parallel start)

### 3. roles/etcd3/cluster/tasks/main.yaml
- [ ] Update to support both `create` and `deploy` actions
- [ ] Keep backup role call only for `deploy` action

### 4. playbooks/etcd-cluster.yaml
- [ ] Update documentation to clarify CREATE vs DEPLOY

### 5. playbooks/upgrade-cluster.yaml
- [ ] Change to use `etcd_action=deploy` instead of `upgrade`
- [ ] Update documentation

### 6. playbooks/restore-etcd-cluster.yaml
- [ ] Ensure it uses CREATE path for parallel start
- [ ] Set etcd_cluster_state: new

### 7. playbooks/deploy-all-clusters.yaml
- [ ] Update to handle both create and deploy actions properly

### 8. README.md
- [ ] Update action documentation
- [ ] Clarify CREATE (first time) vs DEPLOY (updates/upgrades)
- [ ] Remove confusing "upgrade" action (it's just deploy with new version)

## Detailed Changes by File

### roles/etcd3/cluster/install/tasks/0010_cluster.yaml

Current problems:
- Complex state detection with `etcd_new_cluster`, `cluster_members_raw`, `etcd_data.stat.exists`
- Tries to detect if cluster is new or existing
- Has both parallel start and serial restart logic mixed together

New structure:
```yaml
# Early in file, determine mode based on action
- name: Set cluster mode based on action
  set_fact:
    cluster_mode: "{{ 'new' if etcd_action == 'create' else 'existing' }}"

# CREATE MODE SECTION
- name: CREATE | Validate and prepare for new cluster
  when: cluster_mode == 'new'
  block:
    - name: CREATE | Optional force cleanup
    - name: CREATE | Check disk space
    - name: CREATE | Create directories
    - name: CREATE | Generate config with initial-cluster-state: new
    - name: CREATE | Start ALL nodes in parallel (no wait)
    - name: CREATE | Wait for cluster to form

# DEPLOY MODE SECTION  
- name: DEPLOY | Backup before changes
  when: cluster_mode == 'existing'
  
- name: DEPLOY | Validate cluster health
  when: cluster_mode == 'existing'

- name: DEPLOY | Check if upgrade needed
  when: cluster_mode == 'existing'

- name: DEPLOY | Update config
  when: cluster_mode == 'existing'
  
- name: DEPLOY | Serial restart if config changed
  when: cluster_mode == 'existing'
  throttle: 1

# FINAL VALIDATION (both modes)
- name: Verify cluster health
```

### Variables to Remove
- `etcd_new_cluster` - no longer needed, use action directly
- Complex state detection logic
- Auto-detection of cluster state

### Variables to Keep/Update
- `etcd_action`: create | deploy (no more upgrade)
- `etcd_force_create`: only used with create action
- `etcd_cluster_state`: set based on action (new | existing)

## Migration Path for Users

Old commands → New commands:

```bash
# Create new cluster
OLD: ansible-playbook etcd.yaml -e etcd_action=create
NEW: ansible-playbook etcd.yaml -e etcd_action=create (unchanged)

# Deploy changes to existing cluster  
OLD: ansible-playbook etcd.yaml -e etcd_action=deploy
NEW: ansible-playbook etcd.yaml -e etcd_action=deploy (unchanged)

# Upgrade cluster
OLD: ansible-playbook etcd.yaml -e etcd_action=upgrade
NEW: ansible-playbook etcd.yaml -e etcd_action=deploy -e etcd_version=vX.Y.Z

# Force new cluster mode (was confusing)
OLD: ansible-playbook etcd.yaml -e etcd_action=deploy -e etcd_new_cluster=true
NEW: ansible-playbook etcd.yaml -e etcd_action=create -e etcd_force_create=true
```

## Testing Checklist

After changes, verify:
- [ ] CREATE: New cluster starts all nodes together
- [ ] CREATE: Can use etcd_force_create=true to cleanup
- [ ] CREATE: No backup is created
- [ ] DEPLOY: Always creates backup first
- [ ] DEPLOY: Restarts nodes one-by-one
- [ ] DEPLOY: Config changes work (serial restart)
- [ ] DEPLOY: Version upgrade works (serial restart)
- [ ] RESTORE: Uses parallel start path
- [ ] Multi-cluster: Both create and deploy work

## Benefits

1. **Clarity**: Action name clearly indicates what will happen
2. **Simplicity**: No complex state detection logic
3. **Safety**: Can't accidentally parallel-start an existing cluster
4. **Predictability**: CREATE always parallel, DEPLOY always serial
5. **Code reduction**: Remove ~100 lines of detection logic

## Implementation Order

1. ✅ Create this TODO file
2. ✅ Update roles/etcd3/defaults/main.yaml (document actions, deprecate etcd_new_cluster)
3. ✅ Refactor roles/etcd3/cluster/install/tasks/0010_cluster.yaml (split CREATE/DEPLOY paths)
4. ✅ Update roles/etcd3/cluster/tasks/main.yaml (backup logic, deprecation warning)
5. ⏭️  Update playbooks (documentation and action names)
6. ⏭️  Update README.md
7. ⏭️  Test all scenarios
8. ⏭️  Remove deprecated variables from docs

## Notes

- Keep backward compatibility warning if `etcd_action=upgrade` is used
- Add deprecation notice for `etcd_new_cluster` variable
- All playbooks that currently use "upgrade" should be updated to use "deploy"
