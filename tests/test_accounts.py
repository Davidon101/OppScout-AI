import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from opportunities.brevo import BrevoEmailBackend
from opportunities.models import Organization, Opportunity, UserData

User = get_user_model()


def make_user(email="ada@example.com", password="correct-horse-9"):
    return User.objects.create_user(username=email, email=email, password=password)


class SignUpTests(TestCase):
    def test_pages_render_without_google_configured(self):
        for name in ("account_login", "account_signup", "account_reset_password"):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, "demo")
        self.assertNotContains(self.client.get(reverse("account_login")), "Continue with Google")

    def test_sign_up_with_email_and_password_logs_in(self):
        response = self.client.post(reverse("account_signup"), {
            "email": "new@example.com", "password1": "a-long-Pass-phrase-7", "password2": "a-long-Pass-phrase-7"})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(email="new@example.com").exists())
        self.assertContains(self.client.get(reverse("opportunities:home")), "Account")

    def test_weak_password_is_refused(self):
        response = self.client.post(reverse("account_signup"), {
            "email": "weak@example.com", "password1": "12345678", "password2": "12345678"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(email="weak@example.com").exists())

    def test_login_with_email(self):
        make_user()
        response = self.client.post(reverse("account_login"), {"login": "ada@example.com", "password": "correct-horse-9"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get(reverse("opportunities:account_home")).status_code, 200)

    def test_password_reset_sends_email_without_revealing_accounts(self):
        make_user()
        self.client.post(reverse("account_reset_password"), {"email": "ada@example.com"})
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/accounts/password/reset/key/", mail.outbox[0].body)
        mail.outbox.clear()
        response = self.client.post(reverse("account_reset_password"), {"email": "nobody@example.com"})
        self.assertEqual(response.status_code, 302)

    def test_old_links_go_to_the_new_pages(self):
        self.assertEqual(self.client.get("/login/")["Location"], "/accounts/login/")
        self.assertEqual(self.client.get("/register/")["Location"], "/accounts/signup/")

    def test_account_page_needs_sign_in(self):
        response = self.client.get(reverse("opportunities:account_home"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])

    def test_guest_nav_offers_sign_in_not_demo(self):
        page = self.client.get(reverse("opportunities:home"))
        self.assertContains(page, "Sign in")
        self.assertContains(page, 'data-auth="0"')
        self.assertNotContains(page, "demo")


class AccountDataTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client.force_login(self.user)
        self.url = reverse("opportunities:account_data")

    def post(self, body, client=None):
        return (client or self.client).post(self.url, json.dumps(body), content_type="application/json")

    def test_guests_get_401(self):
        self.assertEqual(Client().get(self.url).status_code, 401)
        self.assertEqual(Client().post(self.url, "{}", content_type="application/json").status_code, 401)

    def test_round_trip_and_clean(self):
        response = self.post({
            "profile": {"country": "Nigeria", "skills": "Python", "evil": "x", "categories": ["job", 5], "interests": "  "},
            "saved": ["good-slug", "bad slug!", "good-slug", 7],
        })
        self.assertEqual(response.status_code, 200)
        body = self.client.get(self.url).json()
        self.assertEqual(body["profile"], {"country": "Nigeria", "skills": "Python", "categories": ["job"]})
        self.assertEqual(body["saved"], ["good-slug"])
        self.assertEqual(self.client.get(self.url)["Cache-Control"], "no-store")

    def test_each_user_has_only_their_own_data(self):
        self.post({"saved": ["mine"]})
        other = Client()
        other.force_login(make_user("bola@example.com"))
        self.assertEqual(other.get(self.url).json()["saved"], [])

    def test_bad_input_is_rejected(self):
        self.assertEqual(self.client.post(self.url, "not json", content_type="application/json").status_code, 400)
        self.assertEqual(self.post([1, 2]).status_code, 400)

    def test_saved_list_is_capped(self):
        self.post({"saved": [f"s{i}" for i in range(80)]})
        self.assertEqual(len(self.client.get(self.url).json()["saved"]), 50)

    def test_csrf_is_enforced(self):
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.user)
        response = strict.post(self.url, "{}", content_type="application/json")
        self.assertEqual(response.status_code, 403)

    def test_saved_page_includes_listings_saved_on_another_device(self):
        Opportunity.objects.create(
            title="Server Saved Scholarship", slug="server-saved", provider="P", category="scholarship",
            description="d", official_url="https://example.com", status="published")
        self.post({"saved": ["server-saved"]})
        response = self.client.post(reverse("opportunities:saved_list"), {"slugs": ""})
        self.assertContains(response, "Server Saved Scholarship")
        guest = Client().post(reverse("opportunities:saved_list"), {"slugs": ""})
        self.assertNotContains(guest, "Server Saved Scholarship")

    def test_forget_removes_stored_data_only(self):
        self.post({"saved": ["x"], "profile": {"country": "Ghana"}})
        self.client.post(reverse("opportunities:account_forget"))
        self.assertFalse(UserData.objects.filter(user=self.user).exists())
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())


class OrganizationOwnerTests(TestCase):
    ORG = {"name": "Acme Foundation", "org_type": "ngo", "contact_email": "hi@acme.org",
           "website": "https://acme.org", "location": "Abuja, Nigeria", "about": "", "nickname": ""}

    def test_signed_in_registration_links_owner_and_needs_no_key_later(self):
        user = make_user()
        c = Client(); c.force_login(user)
        c.post(reverse("opportunities:org_register"), self.ORG)
        org = Organization.objects.get()
        self.assertEqual(org.owner, user)
        fresh = Client(); fresh.force_login(user)  # new session, no key
        self.assertEqual(fresh.get(reverse("opportunities:org_dashboard")).status_code, 200)

    def test_other_accounts_and_guests_cannot_open_it(self):
        owner = make_user()
        c = Client(); c.force_login(owner)
        c.post(reverse("opportunities:org_register"), self.ORG)
        other = Client(); other.force_login(make_user("bola@example.com"))
        self.assertEqual(other.get(reverse("opportunities:org_dashboard")).status_code, 302)
        self.assertEqual(Client().get(reverse("opportunities:org_dashboard")).status_code, 302)

    def test_first_key_sign_in_links_an_existing_organization(self):
        guest = Client()
        response = guest.post(reverse("opportunities:org_register"), self.ORG)
        key = response.context["key"]
        org = Organization.objects.get()
        self.assertIsNone(org.owner)
        user = make_user()
        c = Client(); c.force_login(user)
        c.post(reverse("opportunities:org_access"), {"key": key})
        org.refresh_from_db()
        self.assertEqual(org.owner, user)

    def test_sign_out_of_org_keeps_the_account_signed_in(self):
        user = make_user()
        c = Client(); c.force_login(user)
        c.post(reverse("opportunities:org_register"), self.ORG)
        c.post(reverse("opportunities:org_leave"))
        self.assertEqual(c.get(reverse("opportunities:account_home")).status_code, 200)


@override_settings(BREVO_API_KEY="test-key", BREVO_SENDER_EMAIL="sender@example.com", BREVO_SENDER_NAME="OppScout AI")
class BrevoBackendTests(TestCase):
    def message(self):
        return mail.EmailMessage("Hello", "Body text", "OppScout AI <sender@example.com>", ["to@example.com"])

    def test_sends_json_to_brevo_with_key_in_header(self):
        seen = {}

        def opener(request, timeout):
            seen["url"], seen["headers"] = request.full_url, dict(request.header_items())
            seen["body"] = json.loads(request.data)
            return mock.MagicMock(__enter__=lambda s: s, __exit__=lambda *a: False)

        sent = BrevoEmailBackend(opener=opener).send_messages([self.message()])
        self.assertEqual(sent, 1)
        self.assertEqual(seen["url"], "https://api.brevo.com/v3/smtp/email")
        self.assertEqual(seen["headers"]["Api-key"], "test-key")
        self.assertEqual(seen["body"]["to"], [{"email": "to@example.com"}])
        self.assertEqual(seen["body"]["sender"]["email"], "sender@example.com")
        self.assertEqual(seen["body"]["textContent"], "Body text")

    def test_failure_raises_unless_silent_and_key_is_never_logged(self):
        import urllib.error

        def opener(request, timeout):
            raise urllib.error.HTTPError(request.full_url, 401, "no", {}, None)

        with self.assertRaises(urllib.error.HTTPError):
            BrevoEmailBackend(opener=opener).send_messages([self.message()])
        with self.assertLogs("opportunities.brevo", "ERROR") as logs:
            self.assertEqual(BrevoEmailBackend(fail_silently=True, opener=opener).send_messages([self.message()]), 0)
        self.assertNotIn("test-key", "\n".join(logs.output))
