# Scaling

Add or remove nodes from your etcd cluster.

## Adding Nodes

### 1. Update Inventory

```ini
[etcd]
etcd-k8s-1
etcd-k8s-2
etcd-k8s-3
etcd-k8s-4  # NEW NODE
```

### 2. Deploy to New Node

```bash
ansible-playbook -i inventory.ini etcd.yaml \
  -e etcd_action=create \
  --limit=etcd-k8s-4 \
  --vault-password-file ~/.vault-pass -b
```

## Removing Nodes

### 1. Remove Member from Cluster

```bash
# Get member ID
etcdctl member list

# Remove member
etcdctl member remove <MEMBER_ID>
```

### 2. Stop Service on Node

```bash
sudo systemctl stop etcd-default-4
sudo systemctl disable etcd-default-4
```

### 3. Update Inventory

Remove the node from your inventory file.

## Related Documentation

- [Cluster Management](cluster-management.md)
