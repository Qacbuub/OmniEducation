"""
Extension points so the school and university modules can plug into the shared admissions flow
without the shared code knowing about classes, programs or credits.

* TARGET_VALIDATORS[tenant_type](tenant, target_id) -> label   (checks the grade level / program exists)
* TARGET_OPTIONS[tenant_type](tenant) -> [{"id", "name"}]       (what an applicant can apply for, public form)
* ENROLLMENT_HANDLERS[tenant_type](request, application, student, data) -> (level_label, section_label)
  (school: class placement; university: matriculation into a program)
"""

TARGET_VALIDATORS = {}
TARGET_OPTIONS = {}
ENROLLMENT_HANDLERS = {}


def register_target_validator(tenant_type):
    def deco(fn):
        TARGET_VALIDATORS[tenant_type] = fn
        return fn
    return deco


def register_target_options(tenant_type):
    def deco(fn):
        TARGET_OPTIONS[tenant_type] = fn
        return fn
    return deco


def register_enrollment_handler(tenant_type):
    def deco(fn):
        ENROLLMENT_HANDLERS[tenant_type] = fn
        return fn
    return deco
