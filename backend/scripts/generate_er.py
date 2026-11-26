"""Write docs/data-model.md: Mermaid ER diagrams generated from the Django models.

Run from the backend folder:  python scripts/generate_er.py
"""
import os
import sys

import django

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
sys.path.insert(0, BACKEND)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
django.setup()
from django.apps import apps
from django.db import models

AREAS = [
    ("Platform, people and accounts", ["core", "people"], None),
    ("Admissions, calendar and finance", ["admissions", "finance"], {"people.Student", "people.Person"}),
    ("Communication and documents", ["comms"], {"people.Student", "core.User", "admissions.Application"}),
    ("School (K-12) module", ["school"], {"people.Student", "admissions.AcademicPeriod", "core.User"}),
    ("University module", ["university"], {"people.Student", "admissions.AcademicPeriod", "core.User"}),
]
SKIP_FIELDS = {"created_at", "updated_at"}
TYPE = {models.CharField: "string", models.TextField: "text", models.EmailField: "string", models.DateField: "date",
        models.DateTimeField: "datetime", models.TimeField: "time", models.BooleanField: "bool",
        models.DecimalField: "decimal", models.IntegerField: "int", models.PositiveIntegerField: "int",
        models.PositiveSmallIntegerField: "int", models.SmallIntegerField: "int", models.JSONField: "json",
        models.FileField: "file", models.UUIDField: "uuid", models.SlugField: "string", models.URLField: "string"}


def ftype(f):
    for cls in type(f).__mro__:
        if cls in TYPE:
            return TYPE[cls]
    return "string"


def name(m):
    return m.__name__


out = ["# Data model (ER diagrams)", "",
       "Generated from the Django models with `python scripts/generate_er.py` (backend folder), so table names, keys and",
       "relationships match the code. Every tenant-owned table also has `tenant_id → core_tenant` (omitted from",
       "the diagrams to keep them readable) plus `created_at` / `updated_at`.", "",
       "Database table name = `<app>_<model>` in lower case, e.g. `people.Student` → `people_student`.", ""]
total = 0
for title, apps_in, externals in AREAS:
    ms = [m for a in apps_in for m in apps.get_app_config(a).get_models()]
    total += len(ms)
    labels = {m._meta.label for m in ms}
    out += [f"## {title}", "", "```mermaid", "erDiagram"]
    rels = []
    for m in ms:
        lines = []
        for f in m._meta.get_fields():
            if not getattr(f, "concrete", False) or f.name in SKIP_FIELDS or f.name == "tenant":
                continue
            if f.many_to_many:
                tgt = f.related_model._meta.label
                if tgt in labels or (externals and tgt in externals):
                    rels.append(f'    {name(m)} }}o--o{{ {name(f.related_model)} : "{f.name}"')
                continue
            if f.is_relation:
                tgt = f.related_model._meta.label
                lines.append(f"        int {f.name}_id FK")
                if tgt in labels or (externals and tgt in externals):
                    card = "|o--o|" if f.one_to_one else "}o--||" if not f.null else "}o--o|"
                    rels.append(f'    {name(m)} {card} {name(f.related_model)} : "{f.name}"')
                continue
            key = " PK" if f.primary_key else (" UK" if f.unique else "")
            lines.append(f"        {ftype(f)} {f.name}{key}")
        out.append(f"    {name(m)} {{")
        out += lines
        out.append("    }")
    out += sorted(set(rels))
    out += ["```", ""]
out.insert(7, f"{total} tables in 7 apps. Start with the overview in [architecture.md](architecture.md#data-model-overview).")
with open(os.path.join(BACKEND, "..", "docs", "data-model.md"), "w", encoding="utf-8") as f:
    f.write("\n".join(out) + "\n")
print(total, "models", len(out), "lines")
