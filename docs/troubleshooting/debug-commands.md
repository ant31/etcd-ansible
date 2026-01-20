# Debug Commands

Useful commands for debugging etcd clusters.

## Cluster Debugging

```bash
# Check cluster health
etcdctl endpoint health --cluster

# Check member list
etcdctl member list -w table

# Check endpoint status
etcdctl endpoint status -w table

# Check alarms
etcdctl alarm list
```

## Certificate Debugging

```bash
# View certificate details
step certificate inspect /etc/etcd/ssl/etcd-k8s-1-peer.crt

# Verify certificate chain
openssl verify -CAfile /etc/etcd/ssl/root_ca.crt /etc/etcd/ssl/etcd-k8s-1-peer.crt

# Check expiration
openssl x509 -in /etc/etcd/ssl/etcd-k8s-1-peer.crt -noout -dates
```

## Service Debugging

```bash
# Check service status
systemctl status etcd-default-1
systemctl status step-ca

# View logs
journalctl -u etcd-default-1 -f
journalctl -u step-ca -f

# Check renewal timers
systemctl list-timers 'step-renew-*'
```

## Network Debugging

```bash
# Test connectivity
nc -zv 10.0.1.10 2379
nc -zv 10.0.1.10 2380
nc -zv 10.0.1.10 9000

# Check listening ports
netstat -tlnp | grep etcd
netstat -tlnp | grep step-ca
```

## Related Documentation

- [Common Issues](common-issues.md)
- [Certificate Problems](certificates.md)
- [Cluster Issues](cluster.md)
