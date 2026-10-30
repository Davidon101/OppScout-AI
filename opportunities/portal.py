"""Organization portal: post and manage opportunities without accounts.

An organization receives a secret management key when it registers. The key is
shown once and only its hash is stored. Entering it starts a short session.
Nothing here is full authentication, and the pages say so plainly.

Content rules:
- New and edited listings go to "pending review" and are published by an
  administrator. Organizations can then pause, close, mark filled or archive.
- Editing a published or paused listing sends it back for review, so a leaked
  key cannot quietly swap a trusted listing for a harmful one.
"""
import json
import secrets
from functools import wraps

from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from . import limits
from .categories import extra_fields_for
from .models import Opportunity, OpportunityRequirement, Organization
from .portal_forms import OpportunityForm, OrganizationForm

S = Opportunity.Status
SESSION_KEY = "org"
SESSION_SECONDS = 8 * 60 * 60

# status -> {action: new status}. Anything not listed is refused.
TRANSITIONS = {
    S.DRAFT: {"submit": S.PENDING, "archive": S.ARCHIVED},
    S.PENDING: {"withdraw": S.DRAFT, "archive": S.ARCHIVED},
    S.PUBLISHED: {"pause": S.PAUSED, "close": S.CLOSED, "fill": S.FILLED, "archive": S.ARCHIVED},
    S.PAUSED: {"resume": S.PUBLISHED, "close": S.CLOSED, "fill": S.FILLED, "archive": S.ARCHIVED},
    S.CLOSED: {"archive": S.ARCHIVED},
    S.FILLED: {"archive": S.ARCHIVED},
    S.EXPIRED: {"archive": S.ARCHIVED},
    S.ARCHIVED: {},
}
EDITABLE = {S.DRAFT, S.PENDING, S.PUBLISHED, S.PAUSED}
ACTION_LABELS = {
    "submit": "Submit for review",
    "withdraw": "Withdraw to draft",
    "pause": "Take offline",
    "resume": "Put back online",
    "close": "Close applications",
    "fill": "Mark as filled",
    "archive": "Archive",
}
STATUS_HELP = {
    S.DRAFT: "Saved, not visible to anyone.",
    S.PENDING: "Waiting for an OppScout administrator to review it.",
    S.PUBLISHED: "Live in the public directory.",
    S.PAUSED: "Taken offline by you. Not visible.",
    S.CLOSED: "Applications closed. Visible only as closed.",
    S.FILLED: "Marked as filled. Visible only as filled.",
    S.EXPIRED: "The deadline has passed.",
    S.ARCHIVED: "Kept for records. Not visible.",
}


def available_actions(status):
    return [(a, ACTION_LABELS[a]) for a in TRANSITIONS.get(status, {})]


def current_org(request):
    data = request.session.get(SESSION_KEY)
    if not (isinstance(data, list) and len(data) == 2):
        return None
    org = Organization.objects.filter(pk=data[0]).first()
    # A new key (issued by an admin) ends older sessions.
    if org and org.key_hash[:16] == data[1]:
        return org
    return None


def start_session(request, org):
    request.session.cycle_key()
    request.session[SESSION_KEY] = [org.pk, org.key_hash[:16]]
    request.session.set_expiry(SESSION_SECONDS)


def org_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        org = current_org(request)
        if org is None:
            return redirect("opportunities:org_access")
        return view(request, org, *args, **kwargs)

    return never_cache(wrapper)


def landing(request):
    return render(request, "portal/landing.html", {"org": current_org(request)})


@never_cache
def register(request):
    form = OrganizationForm(request.POST or None)
    if request.method == "POST":
        if not limits.within_limit(request, "orgreg", 3, per="day"):
            form.add_error(None, "Too many registrations from this connection today. Please try again tomorrow.")
        elif form.is_valid():
            org = form.save(commit=False)
            raw = "ops_" + secrets.token_urlsafe(24)
            org.key_hash = Organization.hash_key(raw)
            org.save()
            start_session(request, org)
            return render(request, "portal/key_created.html", {"org": org, "key": raw})
    return render(request, "portal/register.html", {"form": form, "editing": False})


@never_cache
def access(request):
    error = ""
    if request.method == "POST":
        if not limits.within_limit(request, "orgkey", 20, per="hour"):
            error = "Too many attempts. Please try again later."
        else:
            org = Organization.for_key(request.POST.get("key", ""))
            if org:
                start_session(request, org)
                return redirect("opportunities:org_dashboard")
            error = "That key was not recognised. Check for extra characters, or ask an administrator for a new one."
    return render(request, "portal/access.html", {"error": error})


@require_POST
def leave(request):
    request.session.flush()
    return redirect("opportunities:org_landing")


@org_required
def dashboard(request, org):
    rows = [
        {"opp": opp, "actions": available_actions(opp.status),
         "help": STATUS_HELP.get(opp.status, ""), "editable": opp.status in EDITABLE}
        for opp in org.opportunities.order_by("-updated_at")
    ]
    return render(request, "portal/dashboard.html", {"org": org, "rows": rows})


@org_required
def edit_organization(request, org):
    # Capture the identity first: validating the form changes `org` in place.
    before = (org.name, org.website, org.contact_email)
    form = OrganizationForm(request.POST or None, instance=org)
    saved = False
    if request.method == "POST" and form.is_valid():
        org = form.save(commit=False)
        if (org.name, org.website, org.contact_email) != before:
            org.verified = False  # identity changed, so it must be checked again
        org.save()
        org.opportunities.update(provider=org.name)
        saved = True
    return render(request, "portal/register.html", {"form": form, "editing": True, "org": org, "saved": saved})


def _save_opportunity(org, form, opp, submit):
    cd = form.cleaned_data
    creating = opp is None
    opp = opp or Opportunity(organization=org)
    opp.title = cd["title"]
    opp.provider = org.name
    opp.category = cd["category"]
    opp.description = cd["description"]
    opp.benefits = cd["benefits"]
    opp.country = cd["country"]
    opp.work_mode = cd["work_mode"]
    opp.education_levels = cd["education_levels"]
    opp.eligible_regions = cd["eligible_regions"]
    opp.excluded_regions = cd["excluded_regions"]
    opp.deadline = cd["deadline"]
    opp.official_url = cd["official_url"]
    opp.how_to_apply = cd["how_to_apply"]
    opp.contact_info = cd["contact_info"]
    opp.details = cd["details"]
    opp.source_url = org.website
    opp.last_verified = timezone.localdate()  # declared by the organization

    if creating or opp.status == S.DRAFT:
        opp.status = S.PENDING if submit else S.DRAFT
    elif opp.status in (S.PUBLISHED, S.PAUSED):
        opp.status = S.PENDING  # edits to an approved listing are reviewed again
    # a pending listing stays pending

    with transaction.atomic():
        opp.save()
        opp.requirements.all().delete()
        rows = [
            OpportunityRequirement(opportunity=opp, text=t, requirement_type="mandatory", order=i)
            for i, t in enumerate(cd["mandatory_list"])
        ] + [
            OpportunityRequirement(opportunity=opp, text=t, requirement_type="preferred", order=100 + i)
            for i, t in enumerate(cd["preferred_list"])
        ]
        OpportunityRequirement.objects.bulk_create(rows)
    return opp


def _opportunity_form_view(request, org, opp):
    editing = opp is not None
    if request.method == "POST":
        form = OpportunityForm(request.POST)
        submit = request.POST.get("action") == "submit"
        if not limits.within_limit(request, "orgpost", 30, per="day"):
            form.add_error(None, "Too many submissions today. Please try again tomorrow.")
        elif form.is_valid():
            _save_opportunity(org, form, opp, submit)
            return redirect("opportunities:org_dashboard")
    else:
        form = OpportunityForm.from_opportunity(opp) if editing else OpportunityForm(
            initial={"work_mode": "physical"}
        )
    extras = {k: [f[0] for f in extra_fields_for(k)] for k in dict(Opportunity.Category.choices)}
    return render(
        request,
        "portal/opportunity_form.html",
        {"form": form, "org": org, "opp": opp, "editing": editing,
         "extra_map_json": json.dumps({k: [f"x_{key}" for key in v] for k, v in extras.items()}),
         "reviews_again": editing and opp.status in (S.PUBLISHED, S.PAUSED)},
    )


@org_required
def new_opportunity(request, org):
    return _opportunity_form_view(request, org, None)


@org_required
def edit_opportunity(request, org, pk):
    opp = get_object_or_404(Opportunity, pk=pk, organization=org)
    if opp.status not in EDITABLE:
        return render(request, "portal/not_editable.html", {"opp": opp}, status=409)
    return _opportunity_form_view(request, org, opp)


@require_POST
@org_required
def change_status(request, org, pk):
    opp = get_object_or_404(Opportunity, pk=pk, organization=org)
    new_status = TRANSITIONS.get(opp.status, {}).get(request.POST.get("action", ""))
    if new_status is None:
        return render(request, "portal/not_editable.html", {"opp": opp, "action_refused": True}, status=409)
    opp.status = new_status
    opp.save(update_fields=["status", "updated_at"])
    return redirect("opportunities:org_dashboard")
