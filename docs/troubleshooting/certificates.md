# Certificate Problems

Troubleshooting certificate-related issues.

## Certificate Request Fails

**Symptom:**
```
step ca certificate failed: connection refused
```

**Solution:**
```bash
# Check step-ca health
curl -k https://etcd-k8s-1:9000/health

# Check network connectivity
telnet etcd-k8s-1 9000

# Verify step-ca is running
sudo systemctl status step-ca
```

## Certificate Expired

**Symptom:**
```
x509: certificate has expired
```

**Solution:**
```bash
# Check expiration
step certificate inspect /etc/etcd/ssl/etcd-k8s-1-peer.crt

# Force renewal
sudo systemctl start step-renew-etcd-k8s-1-peer.service

# Reload etcd
sudo systemctl reload etcd-default-1
```

## Renewal Timer Not Working

**Symptom:**
```
Renewal timer exists but certificates not renewing
```

**Solution:**
```bash
# Check timer status
systemctl list-timers 'step-renew-*'

# Check service logs
sudo journalctl -u step-renew-etcd-k8s-1-peer.service

# Test manual renewal
sudo step ca renew --force \
  /etc/etcd/ssl/etcd-k8s-1-peer.crt \
  /etc/etcd/ssl/etcd-k8s-1-peer.key
```

## Related Documentation

- [Common Issues](common-issues.md)
- [Certificate Renewal](../certificates/renewal.md)
- [Debug Commands](debug-commands.md)
