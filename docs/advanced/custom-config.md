# Custom Configurations

Advanced configuration options for etcd.

## Environment Variables

Add custom environment variables:

```yaml
# In group_vars/all/etcd.yml
etcd_extra_vars:
  ETCD_CUSTOM_VAR: "value"
  ETCD_DEBUG: "true"
```

## Systemd Customization

Configure systemd service options:

```yaml
# Resource limits
etcd_systemd_memory_limit: "8G"
etcd_systemd_cpu_limit: "400%"

# Priority
etcd_systemd_nice_level: -10
etcd_systemd_ionice_class: "realtime"
```

## Metrics Configuration

```yaml
etcd_metrics: "extensive"  # Options: basic, extensive
```

## Related Documentation

- [Performance Tuning](performance.md)
- [Variables Reference](../reference/variables.md)
