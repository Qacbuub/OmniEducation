"""Human-readable sequential numbers (INV-2026-00012, STF-0031, …).

The next number is one more than the highest number already used with that prefix, not "how many rows
exist + 1": counting breaks as soon as a row is deleted or numbers were assigned out of order (demo data,
imports), and then the new number collides with an existing one.
"""
import re


def next_code(queryset, field, prefix, width):
    used = queryset.filter(**{f"{field}__startswith": prefix}).values_list(field, flat=True)
    highest = 0
    for value in used:
        m = re.fullmatch(rf"{re.escape(prefix)}(\d+)", value)
        if m:
            highest = max(highest, int(m.group(1)))
    return f"{prefix}{highest + 1:0{width}d}"
