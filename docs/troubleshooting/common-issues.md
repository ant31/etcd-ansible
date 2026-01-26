# Common Issues

Solutions to common problems with etcd-ansible.

## Installation Issues

### SSH Connection Fails

**Symptom:**
```
UNREACHABLE! => {"changed": false, "msg": "Failed to connect", "unreachable": true}
```

**Solution:**
```bash
# Test SSH directly
ssh user@etcd-k8s-1

# Copy SSH key
ssh-copy-id -i ~/.ssh/id_rsa.pub user@etcd-k8s-1

# Test with Ansible
ansible all -i inventory.ini -m ping
```

### step-ca Won't Start

**Symptom:**
```
step-ca.service: Failed with result 'exit-code'
```

**Solution:**
```bash
# Check logs
sudo journalctl -u step-ca -n 100

# Verify CA files
sudo ls -la /etc/step-ca/secrets/

# Test configuration
sudo /opt/bin/step-ca --dry-run /etc/step-ca/config/ca.json
```

### etcd Won't Start

**Symptom:**
```
etcd-default-1.service: Failed to start
```

**Solution:**
```bash
# Check logs
sudo journalctl -u etcd-default-1 -n 100

# Verify certificates
sudo ls -la /etc/etcd/ssl/

# Check certificate validity
sudo openssl verify -CAfile /etc/etcd/ssl/root_ca.crt /etc/etcd/ssl/etcd-k8s-1-peer.crt
```

## Cluster Issues

### Cluster Unhealthy

**Symptom:**
```
endpoint health failed: context deadline exceeded
```

**Solution:**
```bash
# Check each member
for i in 1 2 3; do
  etcdctl --endpoints=https://etcd-k8s-$i:2379 endpoint health
done

# Check member list
etcdctl member list

# Check logs
sudo journalctl -u etcd-default-1 -n 100
```

### Cluster Split-Brain

**Solution:** See [Cluster Issues](cluster.md)

## Related Documentation

- [Certificate Problems](certificates.md)
- [Cluster Issues](cluster.md)
- [Debug Commands](debug-commands.md)
