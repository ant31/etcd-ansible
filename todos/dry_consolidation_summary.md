# DRY Consolidation Summary

## What Changed

Eliminated duplicate code paths between single-cluster and multi-cluster deployments.

### Before (Violated DRY)

```
Single Cluster:
  playbooks/etcd-cluster.yaml
    → roles/etcd3/cluster
      → roles/etcd3/cluster/install

Multi-Cluster:
  playbooks/deploy-all-clusters.yaml
    → roles/etcd3/multi-cluster
      → loops through clusters
      → roles/etcd3/cluster/install

Problem: Same install logic in two different paths!
```

### After (DRY)

```
Any Deployment (1 or N clusters):
  playbooks/etcd-cluster.yaml
    → roles/etcd3/cluster
      → if single: direct import cluster/install
      → if multi: loop with include_role cluster/install

Result: Same code path always!
```

## Files Changed

| File | Change | Reason |
|------|--------|--------|
| `roles/etcd3/facts/tasks/main.yaml` | Always discover clusters | No special flag needed |
| `roles/etcd3/cluster/tasks/main.yaml` | Handle looping internally | DRY - same logic for 1 or N |
| `playbooks/etcd-cluster.yaml` | Works for both modes | One playbook to rule them all |
| `playbooks/deploy-all-clusters.yaml` | Import etcd-cluster.yaml | Backward compat alias |
| `playbooks/upgrade-cluster.yaml` | Use unified logic | Same deploy path |
| `playbooks/restore-etcd-cluster.yaml` | Use CREATE action | Consistent with new actions |
| `roles/etcd3/multi-cluster/` | Mark deprecated | Logic moved to main cluster role |
| `docs/advanced/unified-multi-cluster.md` | Document DRY approach | Clarify architecture |
| `docs/advanced/multi-cluster-config.md` | Update deployment instructions | One playbook |

## What Users See

### Command Line (No Change!)

```bash
# Single cluster
ansible-playbook -i inventory.ini playbooks/etcd-cluster.yaml -e etcd_action=create -b

# Multiple clusters (NOW SAME COMMAND!)
ansible-playbook -i inventory.ini playbooks/etcd-cluster.yaml -e etcd_action=create -b
```

### Configuration (No Change!)

```yaml
# group_vars/all/etcd.yaml

# Single cluster (no etcd_cluster_configs)
etcd_cluster_name: default
etcd_client_port: 2379

# Multiple clusters (define etcd_cluster_configs)
etcd_cluster_configs:
  k8s:
    ports: { client: 2379, peer: 2380 }
  k8s-events:
    ports: { client: 2381, peer: 2382 }
```

## Implementation Details

### Discovery Logic (roles/etcd3/facts)

```yaml
- name: Always discover clusters (if configured)
  when: etcd_cluster_configs is defined
  tasks:
    - Build deployment matrix
    - Validate inventory groups
    - Set _deploying_multiple_clusters flag
```

### Deployment Logic (roles/etcd3/cluster)

```yaml
- name: Single cluster
  import_role: cluster/install
  when: not _deploying_multiple_clusters

- name: Multiple clusters
  include_role: cluster/install
  loop: "{{ _clusters_to_deploy }}"
  when: _deploying_multiple_clusters
```

**Both use the same `cluster/install` role - DRY achieved!**

## Testing

Verify both modes use same code:

```bash
# Test single cluster
ansible-playbook -i inventory-single.ini playbooks/etcd-cluster.yaml -e etcd_action=create -b

# Test multi-cluster (SAME PLAYBOOK)
ansible-playbook -i inventory-multi.ini playbooks/etcd-cluster.yaml -e etcd_action=create -b

# Both execute:
# 1. roles/etcd3/facts (discovers cluster count)
# 2. roles/etcd3/cluster (adapts based on count)
# 3. roles/etcd3/cluster/install (same deployment logic)
```

## Code Reduction

- Removed: ~150 lines of duplicate playbook preparation
- Removed: Separate multi-cluster role looping logic
- Added: ~30 lines for conditional looping in main cluster role
- **Net:** ~120 lines removed, cleaner architecture

## Benefits

1. **DRY Compliance**: No duplicate logic
2. **Easier Maintenance**: Fix once, benefits all deployments
3. **Better Testing**: Test multi-cluster = test single-cluster
4. **User Simplicity**: One playbook for everything
5. **Consistent Behavior**: Same validation, safety checks, error messages

## Deprecation Path

**Phase 1** (Current):
- ✅ DRY consolidation complete
- ✅ Old playbooks redirect to new unified approach
- ✅ Deprecation warnings displayed

**Phase 2** (Next release):
- Remove `playbooks/deploy-all-clusters.yaml`
- Remove `roles/etcd3/multi-cluster/`
- Update all docs to reference single playbook

**Phase 3** (Future):
- Remove `etcd_deploy_all_clusters` flag (no longer needed)
- Clean up compatibility shims
