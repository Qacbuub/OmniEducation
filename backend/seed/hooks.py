"""School and university modules register extra demo data here (keeps the modules separate).

HOOKS: fn(command, school=Tenant, university=Tenant)
RESET_HOOKS: fn(tenants_queryset) - delete module data before the shared data is removed
"""
HOOKS = []
RESET_HOOKS = []
