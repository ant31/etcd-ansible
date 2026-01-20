# Smallstep CA

Detailed guide to Smallstep CA integration.

## What is Smallstep CA?

Smallstep CA (step-ca) is a modern certificate authority that provides:

- Automated certificate issuance
- Built-in renewal mechanisms
- ACME protocol support
- REST API for certificate requests
- Certificate lifecycle management

## How It Works

### 1. step-ca Service

Runs on cert-manager node (port 9000):

```bash
# Check status
sudo systemctl status step-ca

# View logs
sudo journalctl -u step-ca -f

# Test health
curl -k https://localhost:9000/health
```

### 2. Certificate Request Flow

```
Node → step CLI → step-ca (HTTPS) → Sign → Return cert
```

Each node uses step CLI to request certificates:

```bash
step ca certificate "etcd-k8s-1" \
  /etc/etcd/ssl/etcd-k8s-1-peer.crt \
  /etc/etcd/ssl/etcd-k8s-1-peer.key \
  --ca-url=https://10.0.1.10:9000
```

### 3. Automatic Renewal

Systemd timers renew certificates before expiration:

```bash
# Check renewal timers
systemctl list-timers 'step-renew-*'

# Trigger manual renewal
systemctl start step-renew-etcd-k8s-1-peer.service
```

## Configuration

### Certificate Lifetimes

Default configuration in `roles/etcd3/certs/smallstep/defaults/main.yml`:

```yaml
step_cert_default_duration: "17520h"  # 2 years
step_cert_max_duration: "26280h"      # 3 years
step_cert_min_duration: "1h"
```

### Renewal Schedule

Certificates renew at 2/3 of their lifetime:

- 2-year cert: Renews at ~487 days
- 1-year cert: Renews at ~243 days

## Related Documentation

- [Certificate Overview](overview.md)
- [Certificate Renewal](renewal.md)
- [Disaster Recovery](disaster-recovery.md)
