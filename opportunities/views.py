import re
from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.db.models import Count, F, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.decorators.vary import vary_on_headers

from ai_engine import eligibility as elig
from ai_engine import gap_analysis as gaps_engine
from ai_engine.matching import rank_opportunities
from ai_engine.profile import Profile
from ai_engine.providers import ProviderError, ProviderUnavailable
from ai_engine.regions import COUNTRY_NAMES

from . import limits
from .forms import ProfileForm
from .services import get_provider
from .models import Opportunity, OpportunityRequirement

PAGE_SIZE = 12


def home(request):
    featured = list(
        Opportunity.objects.published()
        .open()
        .order_by(F("deadline").asc(nulls_last=True), "title")[:3]
    )
    sample = Profile.from_mapping({
        "country": "Nigeria",
        "education_level": "undergraduate",
        "field_of_study": "Computer Science",
        "skills": "Python, HTML",
        "interests": "software development, AI engineering",
    })
    open_listings = list(Opportunity.objects.published().open().prefetch_related("requirements"))
    sample_matches = rank_opportunities(sample, open_listings, today=timezone.localdate()).matches[:3]
    live = Opportunity.objects.published().open()
    counts = dict(live.values_list("category").annotate(n=Count("id")).values_list("category", "n"))
    type_tiles = [(v, label, counts.get(v, 0)) for v, label in Opportunity.Category.choices]
    return render(
        request,
        "home.html",
        {
            "type_tiles": type_tiles,
            "live_count": live.count(),
            "featured": featured,
            "categories": Opportunity.Category.choices,
            "sample_matches": sample_matches,
        },
    )


def healthz(request):
    """Plain liveness check. Deliberately does not touch the database."""
    return JsonResponse({"status": "ok"})


def login_demo(request):
    return render(request, "accounts/login.html")


def register_demo(request):
    return render(request, "accounts/register.html")


def clean_filters(params):
    """Normalise GET params. Unknown or invalid values become empty strings."""
    category = params.get("category", "")
    level = params.get("education_level", "")
    mode = params.get("work_mode", "")
    return {
        "q": params.get("q", "").strip()[:100],
        "category": category if category in Opportunity.Category.values else "",
        "country": params.get("country", "").strip()[:100],
        "education_level": level if level in Opportunity.EducationLevel.values else "",
        "work_mode": mode if mode in Opportunity.WorkMode.values else "",
        "include_closed": "1" if params.get("include_closed") == "1" else "",
    }


def filter_opportunities(filters):
    qs = Opportunity.objects.visible() if filters["include_closed"] else Opportunity.objects.published()
    if filters["q"]:
        qs = qs.filter(
            Q(title__icontains=filters["q"])
            | Q(provider__icontains=filters["q"])
            | Q(description__icontains=filters["q"])
        )
    if filters["category"]:
        qs = qs.filter(category=filters["category"])
    if filters["country"]:
        # Listings with no country are open to everyone, so they always match.
        qs = qs.filter(Q(country__iexact=filters["country"]) | Q(country=""))
    if filters["education_level"]:
        # JSON list lookups are not portable between SQLite and PostgreSQL, and
        # the dataset is small, so decide in Python and filter by primary key.
        level = filters["education_level"]
        ids = [
            o.pk for o in qs.only("id", "education_levels") if o.accepts_education(level)
        ]
        qs = qs.filter(pk__in=ids)
    if filters["work_mode"]:
        qs = qs.filter(work_mode=filters["work_mode"])
    if not filters["include_closed"]:
        qs = qs.open()
    return qs.order_by(F("deadline").asc(nulls_last=True), "title")


@vary_on_headers("HX-Request")
def opportunity_list(request):
    filters = clean_filters(request.GET)
    page = Paginator(filter_opportunities(filters), PAGE_SIZE).get_page(
        request.GET.get("page")
    )
    querystring = urlencode({k: v for k, v in filters.items() if v})

    if request.headers.get("HX-Request"):
        template = "opportunities/partials/results.html"
    else:
        template = "opportunities/list.html"

    countries = (
        Opportunity.objects.published()
        .exclude(country="")
        .order_by("country")
        .values_list("country", flat=True)
        .distinct()
    )
    context = {
        "page": page,
        "filters": filters,
        "querystring": querystring,
        "categories": Opportunity.Category.choices,
        "levels": Opportunity.EducationLevel.choices,
        "modes": Opportunity.WorkMode.choices,
        "countries": list(countries),
    }
    return render(request, template, context)


def opportunity_detail(request, slug):
    opp = get_object_or_404(Opportunity.objects.visible(), slug=slug)
    requirements = list(opp.requirements.all())
    by_type = OpportunityRequirement.RequirementType
    context = {
        "opp": opp,
        "mandatory": [r for r in requirements if r.requirement_type == by_type.MANDATORY],
        "preferred": [r for r in requirements if r.requirement_type == by_type.PREFERRED],
        "unclear": [r for r in requirements if r.requirement_type == by_type.UNCLEAR],
        "has_requirements": bool(requirements),
        "ai_available": opp.status in (Opportunity.Status.PUBLISHED, Opportunity.Status.EXPIRED),
    }
    return render(request, "opportunities/detail.html", context)


def profile_form(request):
    return render(
        request,
        "profile/form.html",
        {"form": ProfileForm(), "country_options": COUNTRY_NAMES},
    )


@require_POST
@vary_on_headers("HX-Request")
def match_results(request):
    """Rank listings for a profile sent in the request. The profile is not stored."""
    form = ProfileForm(request.POST)
    context = {"form": form, "result": None, "profile": None}
    if form.is_valid():
        profile = form.to_profile()
        if profile.is_empty():
            form.add_error(
                None,
                "Add at least one detail, such as your country, education level, "
                "skills or interests.",
            )
        else:
            opportunities = list(
                Opportunity.objects.published().open().prefetch_related("requirements")
            )
            context["result"] = rank_opportunities(
                profile, opportunities, today=timezone.localdate()
            )
            context["profile"] = profile

    if request.headers.get("HX-Request"):
        template = "matching/partials/match_list.html"
    else:
        template = "matching/results.html"
    response = render(request, template, context)
    response["Cache-Control"] = "no-store"
    return response


@require_POST
@vary_on_headers("HX-Request")
def eligibility_check(request, slug):
    """Compare the visitor's profile with one listing's stored requirements.

    The profile arrives in the request, is sent (in part) to the AI provider,
    and is never stored or logged.
    """
    opp = get_object_or_404(
        Opportunity.objects.filter(
            status__in=[Opportunity.Status.PUBLISHED, Opportunity.Status.EXPIRED]
        ),
        slug=slug,
    )
    context = {"opp": opp, "assessment": None, "message": "", "closed": opp.is_expired}
    form = ProfileForm(request.POST)
    if not form.is_valid():
        context["message"] = "Some profile details were not valid. Check your profile and try again."
    else:
        profile = form.to_profile()
        context.update(_run_eligibility(request, opp, profile))

    template = (
        "eligibility/partials/result.html"
        if request.headers.get("HX-Request")
        else "eligibility/result.html"
    )
    response = render(request, template, context)
    response["Cache-Control"] = "no-store"
    return response


def _run_eligibility(request, opp, profile):
    if not elig.has_assessable_details(profile):
        return {"message": "Add your details on the profile page first. Your profile is kept in this browser and nothing is checked without it."}

    requirements = [
        {"id": r.pk, "text": r.text, "type": r.requirement_type}
        for r in opp.requirements.all()
    ]
    checks = elig.rule_checks(
        profile, opp.education_levels, opp.eligible_regions, opp.excluded_regions
    )

    if any(c.status == elig.NOT_MET and c.label.startswith("Where") for c in checks):
        # The listing states regions that exclude the visitor. No AI call needed.
        return {"assessment": elig.rules_only_assessment(checks)}
    if not requirements:
        return {
            "assessment": elig.Assessment(
                verdict=elig.NO_REQUIREMENTS if not checks else elig.overall_verdict((), checks),
                rule_checks=checks,
            ),
            "message": "No requirements are recorded for this listing, so there is nothing to assess. See the official page.",
        }

    try:
        provider = get_provider()
    except ProviderUnavailable as exc:
        return {"message": exc.public_message, "assessment": elig.rules_only_assessment(checks) if checks else None}

    try:
        limits.reserve(request)
    except limits.LimitExceeded as exc:
        return {"message": exc.public_message}

    system, user, schema = elig.build_request(
        profile, {"title": opp.title, "provider": opp.provider}, requirements
    )
    try:
        raw = provider.generate_json(system, user, schema)
    except ProviderError as exc:
        return {"message": exc.public_message}
    return {"assessment": elig.parse_assessment(raw, requirements, checks)}


@require_POST
@vary_on_headers("HX-Request")
def gap_analysis(request, slug):
    """Suggest next steps for the requirements the visitor does not yet clearly meet.

    Same privacy and cap rules as the eligibility check.
    """
    opp = get_object_or_404(
        Opportunity.objects.filter(
            status__in=[Opportunity.Status.PUBLISHED, Opportunity.Status.EXPIRED]
        ),
        slug=slug,
    )
    context = {"opp": opp, "report": None, "checks": (), "message": "", "closed": opp.is_expired}
    form = ProfileForm(request.POST)
    if not form.is_valid():
        context["message"] = "Some profile details were not valid. Check your profile and try again."
    else:
        context.update(_run_gaps(request, opp, form.to_profile()))

    template = (
        "gaps/partials/result.html" if request.headers.get("HX-Request") else "gaps/result.html"
    )
    response = render(request, template, context)
    response["Cache-Control"] = "no-store"
    return response


def _run_gaps(request, opp, profile):
    if not elig.has_assessable_details(profile):
        return {"message": "Add your details on the profile page first. Your profile is kept in this browser and nothing is analysed without it."}

    checks = elig.rule_checks(
        profile, opp.education_levels, opp.eligible_regions, opp.excluded_regions
    )
    if any(c.status == elig.NOT_MET and c.label.startswith("Where") for c in checks):
        return {
            "checks": checks,
            "message": "This listing's stated regions do not include your country. Building skills will not change that, so check the official page before investing time.",
        }

    requirements = [
        {"id": r.pk, "text": r.text, "type": r.requirement_type}
        for r in opp.requirements.all()
    ]
    if not requirements:
        return {"checks": checks, "message": "No requirements are recorded for this listing, so there is nothing to compare. See the official page."}

    try:
        provider = get_provider()
    except ProviderUnavailable as exc:
        return {"checks": checks, "message": exc.public_message}
    try:
        limits.reserve(request)
    except limits.LimitExceeded as exc:
        return {"checks": checks, "message": exc.public_message}

    system, user, schema = gaps_engine.build_request(
        profile, {"title": opp.title, "provider": opp.provider}, requirements
    )
    try:
        raw = provider.generate_json(system, user, schema)
    except ProviderError as exc:
        return {"checks": checks, "message": exc.public_message}
    return {"checks": checks, "report": gaps_engine.parse_gaps(raw, requirements)}


SAVED_MAX = 50
_SLUG_RE = re.compile(r"^[-a-zA-Z0-9_]{1,200}$")


def saved_page(request):
    return render(request, "saved/page.html")


@require_POST
@vary_on_headers("HX-Request")
def saved_list(request):
    """Cards for the slugs the browser has saved. The list itself is never stored."""
    slugs = [
        s for s in dict.fromkeys(request.POST.get("slugs", "").split(","))
        if _SLUG_RE.match(s)
    ][:SAVED_MAX]
    found = {
        o.slug: o
        for o in Opportunity.objects.visible().filter(slug__in=slugs)
    }
    ordered = [found[s] for s in slugs if s in found]
    response = render(
        request,
        "saved/partials/list.html",
        {"opportunities": ordered, "missing": len(slugs) - len(ordered)},
    )
    response["Cache-Control"] = "no-store"
    return response
