# Certificate Renewal

Automated and manual certificate renewal procedures.

## Automatic Renewal

Certificates automatically renew via systemd timers.

### Check Renewal Timers

```bash
# List all renewal timers
systemctl list-timers 'step-renew-*'

# Check specific timer
systemctl status step-renew-etcd-k8s-1-peer.timer
```

### Renewal Schedule

- **When**: Daily at 3:00 AM (± 1 hour random delay)
- **Trigger**: Certificate has < 1/3 lifetime remaining
- **Action**: Renew certificate and reload etcd

## Manual Renewal

### Renew Single Certificate

```bash
# Renew peer certificate
sudo systemctl start step-renew-etcd-k8s-1-peer.service

# Check renewal logs
sudo journalctl -u step-renew-etcd-k8s-1-peer.service -n 20
```

### Renew All Certificates

```bash
# On a single node
sudo systemctl start step-renew-etcd-k8s-1-peer.service
sudo systemctl start step-renew-etcd-k8s-1-server.service
sudo systemctl start step-renew-etcd-k8s-1-client.service
```

### Using Ansible

```bash
# Renew certificates on all nodes
ansible etcd -i inventory.ini -m systemd \
  -a "name=step-renew-etcd-default-1-peer.service state=started" -b
```

## Troubleshooting Renewal

### Renewal Fails

```bash
# Check step-ca health
curl -k https://etcd-k8s-1:9000/health

# Check renewal service logs
sudo journalctl -u step-renew-etcd-k8s-1-peer.service

# Test manual renewal
sudo step ca renew --force \
  /etc/etcd/ssl/etcd-k8s-1-peer.crt \
  /etc/etcd/ssl/etcd-k8s-1-peer.key
```

## Related Documentation

- [Certificate Overview](overview.md)
- [Smallstep CA](smallstep.md)
- [Disaster Recovery](disaster-recovery.md)
