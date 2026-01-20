# Certificate Management Overview

Complete guide to certificate management with Smallstep CA.

## Architecture

etcd-ansible uses Smallstep CA (step-ca) for automated certificate management:

- **step-ca** runs on cert-manager nodes
- **2-year certificate lifetime** (configurable)
- **Automatic renewal** via systemd timers
- **Zero-downtime rotation**
- **Private keys never transmitted**

## Certificate Types

### Root CA Certificate
- Lifetime: 10 years
- Location: `/etc/step-ca/certs/root_ca.crt`
- Purpose: Trust anchor for all certificates

### Intermediate CA Certificate
- Lifetime: 10 years
- Location: `/etc/step-ca/certs/intermediate_ca.crt`
- Purpose: Signs node certificates

### Node Certificates

Each etcd node has three certificates:

1. **Peer Certificate** - For etcd peer-to-peer communication
2. **Server Certificate** - For client-to-server communication
3. **Client Certificate** - For this node to act as a client

## Certificate Locations

```
/etc/etcd/ssl/
├── etcd-k8s-1-peer.crt     # Peer certificate
├── etcd-k8s-1-peer.key     # Peer private key
├── etcd-k8s-1-server.crt   # Server certificate
├── etcd-k8s-1-server.key   # Server private key
├── etcd-k8s-1-client.crt   # Client certificate
├── etcd-k8s-1-client.key   # Client private key
├── root_ca.crt             # Root CA
├── peer-ca.crt → root_ca.crt
└── client-ca.crt → root_ca.crt
```

## Related Documentation

- [Smallstep CA Details](smallstep.md)
- [Certificate Renewal](renewal.md)
- [Disaster Recovery](disaster-recovery.md)
