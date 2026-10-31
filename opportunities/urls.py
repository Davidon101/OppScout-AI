from django.urls import path

from . import portal, views

app_name = "opportunities"

urlpatterns = [
    path("", views.home, name="home"),
    path("healthz/", views.healthz, name="healthz"),
    path("account-data/", views.account_data, name="account_data"),
    path("account/", views.account_home, name="account_home"),
    path("account/forget/", views.account_forget, name="account_forget"),
    path("login/", views.login_page, name="login"),
    path("register/", views.register_page, name="register"),
    path("profile/", views.profile_form, name="profile"),
    path("matches/", views.match_results, name="matches"),
    path("opportunities/", views.opportunity_list, name="list"),
    path("opportunities/<slug:slug>/", views.opportunity_detail, name="detail"),
    path("for-organizations/", portal.landing, name="org_landing"),
    path("for-organizations/register/", portal.register, name="org_register"),
    path("for-organizations/access/", portal.access, name="org_access"),
    path("for-organizations/leave/", portal.leave, name="org_leave"),
    path("for-organizations/dashboard/", portal.dashboard, name="org_dashboard"),
    path("for-organizations/profile/", portal.edit_organization, name="org_profile"),
    path("for-organizations/opportunities/new/", portal.new_opportunity, name="org_new"),
    path("for-organizations/opportunities/<int:pk>/edit/", portal.edit_opportunity, name="org_edit"),
    path("for-organizations/opportunities/<int:pk>/status/", portal.change_status, name="org_status"),
    path("saved/", views.saved_page, name="saved"),
    path("saved/list/", views.saved_list, name="saved_list"),
    path("opportunities/<slug:slug>/gaps/", views.gap_analysis, name="gaps"),
    path("opportunities/<slug:slug>/check/", views.eligibility_check, name="check"),
]
