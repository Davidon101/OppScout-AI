"""Extra fields that only make sense for some categories.

The form shows these after the common fields. The server keeps only the fields
that belong to the chosen category, so a scholarship can never carry a salary.
Values are stored in Opportunity.details as short text.
"""

EMPLOYMENT_TYPES = ("Full-time", "Part-time", "Contract", "Temporary", "Volunteer")

# category -> list of (key, label, kind). kind is "text" or "choice:<name>".
EXTRA_FIELDS = {
    "scholarship": [
        ("degree_level", "Degree level", "text"),
        ("eligible_courses", "Eligible courses or fields", "text"),
        ("funding_coverage", "What the funding covers", "text"),
    ],
    "job": [
        ("employment_type", "Employment type", "choice:employment"),
        ("experience_required", "Experience required", "text"),
        ("salary_range", "Salary range (only if you disclose it)", "text"),
        ("required_skills", "Required skills", "text"),
    ],
    "internship": [
        ("duration", "Duration", "text"),
        ("stipend", "Stipend (only if offered)", "text"),
        ("required_skills", "Required skills", "text"),
    ],
    "fellowship": [
        ("duration", "Duration", "text"),
        ("stipend", "Stipend (only if offered)", "text"),
        ("selection_process", "Selection process", "text"),
    ],
    "grant": [
        ("funding_amount", "Funding amount or range", "text"),
        ("use_of_funds", "What the funds can be used for", "text"),
    ],
    "training": [
        ("duration", "Duration", "text"),
        ("cost", "Cost (write Free if free)", "text"),
        ("certification", "Certificate offered", "text"),
    ],
}

DETAIL_MAX = 200


def extra_fields_for(category):
    return EXTRA_FIELDS.get(category, [])


def all_extra_keys():
    seen = {}
    for fields in EXTRA_FIELDS.values():
        for key, label, kind in fields:
            seen.setdefault(key, (label, kind))
    return seen


def clean_details(category, raw):
    """Keep only this category's fields, as short single-line text."""
    allowed = {k for k, _, _ in extra_fields_for(category)}
    out = {}
    for key, value in (raw or {}).items():
        if key in allowed:
            text = " ".join(str(value or "").split())[:DETAIL_MAX]
            if key == "employment_type" and text not in EMPLOYMENT_TYPES:
                text = ""
            if text:
                out[key] = text
    return out


def details_for_display(category, details):
    """[(label, value)] in the category's own order."""
    out = []
    for key, label, _ in extra_fields_for(category):
        value = (details or {}).get(key)
        if value:
            out.append((label.split(" (")[0], value))
    return out
