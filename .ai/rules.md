# Ansible Architecture Rules

## CRITICAL: Task Organization

**NEVER write tasks directly in playbooks. ALL tasks MUST be inside roles.**

### ✅ Correct Pattern

```yaml
# playbooks/example.yaml
---
- hosts: etcd
  gather_facts: yes
  vars:
    operation_action: status
  roles:
    - role: etcd3/operations
```

```yaml
# roles/etcd3/operations/tasks/main.yml
---
- name: Show cluster status
  include_tasks: status.yml
  when: operation_action == 'status'
```

### ❌ WRONG - DO NOT DO THIS

```yaml
# playbooks/example.yaml - WRONG!
---
- hosts: etcd
  tasks:
    - name: Get cluster status
      command: etcdctl endpoint status
      register: status
    
    - name: Display status
      debug:
        var: status
```

## Role-Based Architecture

### Playbook Responsibilities (ONLY)

1. **Set variables** - Pass configuration to roles
2. **Import roles** - Delegate work to roles
3. **Define host groups** - Which hosts to target
4. **Orchestration** - Control flow between roles (serial, when, tags)

### Role Responsibilities

1. **All task implementation** - Every actual ansible task
2. **Task organization** - Break complex operations into subtasks
3. **Reusability** - Roles can be used by multiple playbooks
4. **Defaults and variables** - Configuration management

## When Playbooks Can Have Tasks

**ONLY for orchestration and validation:**

1. **Pre-flight checks** - Validate parameters before calling roles
2. **Confirmations** - User prompts before destructive operations  
3. **Final reporting** - Summary information after roles complete

**Example of acceptable playbook tasks:**

```yaml
---
- name: Validate parameters
  hosts: localhost
  gather_facts: no
  tasks:
    - name: Check required variable
      assert:
        that: some_var is defined
        fail_msg: "Variable required"

- name: Confirm destructive action
  hosts: localhost
  gather_facts: no
  tasks:
    - name: Prompt user
      pause:
        prompt: "Type 'yes' to confirm"
      register: confirm
    
    - name: Validate
      assert:
        that: confirm.user_input == 'yes'

- name: Do the actual work
  hosts: etcd
  roles:
    - role: etcd3/operations  # <-- Real work in role
      vars:
        operation_action: delete

- name: Display results
  hosts: localhost
  gather_facts: no
  tasks:
    - debug:
        msg: "Operation complete"
```

## Directory Structure

```
playbooks/
  ├── operation1.yaml          # Thin, imports roles
  ├── operation2.yaml          # Thin, imports roles
  └── operation3.yaml          # Thin, imports roles

roles/
  └── etcd3/
      ├── operations/
      │   └── tasks/
      │       ├── main.yml     # Router task
      │       ├── status.yml   # Actual implementation
      │       └── members.yml  # Actual implementation
      ├── cluster/
      │   └── tasks/
      │       └── ...          # Actual implementation
      └── backups/
          └── tasks/
              └── ...          # Actual implementation
```

## Why This Matters

1. **Reusability** - Roles can be called from different playbooks
2. **Testing** - Roles can be tested independently
3. **Maintenance** - Logic in one place, not scattered across playbooks
4. **Composition** - Complex workflows built from simple role combinations
5. **Defaults** - Roles have their own defaults, playbooks just override

## Summary

**If you're writing actual ansible tasks (command, shell, copy, template, etc.), it MUST be in a role, not a playbook.**

Playbooks are thin orchestration layers. Roles contain all implementation.

---

# Variable Duplication Pattern (Self-Documenting Bubble-Up)

## CRITICAL: Define Variables in BOTH Places

Every role MUST define 100% of its variables in its own `defaults/main.yml` for self-documentation.

These variables MUST ALSO be duplicated in `roles/etcd3/defaults/main.yaml` for cross-role access.

### ✅ Correct Pattern

**Step 1:** Define all variables in the role's defaults (self-documenting):

```yaml
# roles/etcd3/backups/ca/defaults/main.yml
---
# CA backup configuration
step_ca_backup_encryption_method: "aws-kms"
step_ca_backup_s3_bucket: "etcd-backups"
step_ca_backup_s3_prefix: "step-ca"
step_ca_backup_s3_enabled: true
```

**Step 2:** Duplicate the SAME variables in root defaults (bubbling up):

```yaml
# roles/etcd3/defaults/main.yaml
---
# ... other variables ...

# ============================================================================
# CA BACKUP CONFIGURATION (used by roles/etcd3/backups/ca)
# ============================================================================
step_ca_backup_encryption_method: "aws-kms"
step_ca_backup_s3_bucket: "etcd-backups"
step_ca_backup_s3_prefix: "step-ca"
step_ca_backup_s3_enabled: true
```

**Step 3:** Use the variables in any role:

```yaml
# roles/etcd3/backups/ca/tasks/main.yml
---
- name: Upload to S3
  command: aws s3 cp backup.tar.gz s3://{{ step_ca_backup_s3_bucket }}/{{ step_ca_backup_s3_prefix }}/
  when: step_ca_backup_s3_enabled  # DEFINED - won't fail!
```

### Why This Duplication?

1. **Self-Documentation**: Each role's defaults file shows ALL variables that role uses
2. **Cross-Role Access**: Root defaults ensure variables are available everywhere
3. **Prevents "undefined" errors**: Variables loaded via etcd3 meta dependency
4. **Easy Discovery**: Look at role's defaults to see what it needs
5. **Consistency**: Same defaults used everywhere

### Enforcement Rules

For EVERY role:

1. **100% Variable Definition**: ALL variables used in role MUST be in `roles/my_role/defaults/main.yml`
2. **Bubble Up**: ALL those variables MUST ALSO be in `roles/etcd3/defaults/main.yaml`
3. **Same Defaults**: Use identical default values in both places
4. **Comment Origin**: In root defaults, comment which role uses the variable
5. **Meta Dependency**: Role MUST depend on `etcd3` to load root defaults

### Checklist for Adding New Variables

When adding a new variable to any role:

- [ ] Added to role's `defaults/main.yml`?
- [ ] Duplicated in `roles/etcd3/defaults/main.yaml`?
- [ ] Same default value in both places?
- [ ] Commented in root defaults which role uses it?
- [ ] Role has etcd3 meta dependency?
- [ ] Tested that it works from other roles?

## Variable Naming for Bubble-Up

- Use globally unique prefixes: `etcd_*`, `step_ca_*`, `backup_*`
- Avoid generic names that might conflict: `port`, `enabled`, `path`
- Be specific: `step_ca_backup_s3_enabled` not `s3_enabled`
