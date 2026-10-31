# Accounts: Google sign-in and email (Brevo)

Accounts are optional. Guests keep working exactly as before. Signed-in visitors get their profile and saved list stored on their account (so they follow them between devices), and organizations can be managed from an account without a key.

Nothing here costs money. Every secret goes only into Render's environment form (Dashboard > your service > Environment). Never paste a secret in chat, in code, or in GitHub.

Until you finish a step below, that feature is simply off: no Google button without the Google variables, and no email verification without the Brevo variables.

## 1. Google sign-in

1. Go to console.cloud.google.com and create a project (any name, for example OppScout).
2. Open APIs & Services > OAuth consent screen. Choose External. Fill in the app name (OppScout AI), your email as support and developer contact. Save.
3. Under the same area, set the publishing status to **In production** ("Publish app"). While it says Testing, only people you add as test users can sign in. The basic scopes OppScout asks for (email and profile) do not need Google's verification.
4. Open APIs & Services > Credentials > Create credentials > OAuth client ID. Type: Web application.
5. Authorized redirect URI (copy exactly, using your real Render address):
   `https://YOUR-SERVICE.onrender.com/accounts/google/login/callback/`
6. Create. Copy the Client ID and Client secret.
7. In Render > Environment add:
   - `GOOGLE_CLIENT_ID`
   - `GOOGLE_CLIENT_SECRET`
8. Save. Render redeploys. A "Continue with Google" button now appears on the sign-in and sign-up pages.

## 2. Email through Brevo

Render's free tier blocks SMTP ports, so OppScout sends mail through Brevo's web API instead.

1. Create a free account at brevo.com.
2. Add and verify a sender: the address emails will come from. Brevo emails that address a confirmation link.
3. Create an API key (in Brevo's account settings under SMTP & API). Copy it once.
4. In Render > Environment add:
   - `BREVO_API_KEY` (the key)
   - `BREVO_SENDER_EMAIL` (the verified sender address)
   - `BREVO_SENDER_NAME` (optional, defaults to OppScout AI)
5. Save. Render redeploys. Email sign-up now requires visitors to confirm their address, and password reset emails are sent.

Limits and cautions:
- Brevo's free plan allows 300 emails a day.
- A Gmail address as the sender often lands in spam, because the mail is not sent from Gmail's own servers. A domain you own, with Brevo's DNS records added, fixes this. Test by signing up with a second address and checking the spam folder.
- Without the Brevo variables, verification is off and emails are only printed to Render's log (so password reset will not reach people). Set Brevo up before telling people to use passwords.

## 3. What gets stored

Per signed-in user: the email address, a hashed password (none for Google-only users), the profile fields they typed, and the list of saved listing slugs. Visitors can remove the profile and list from the My account page. Guests store nothing on the server.

Before launching widely, add a privacy notice and a way to delete the account entirely (currently an admin deletes the user in Django Admin).

## 4. Organizations

- Register an organization while signed in and it is linked to your account. You open its dashboard without a key.
- An existing key-based organization links to your account the first time you sign in with its key.
- The key still works as a backup. An admin can still issue a new one.
- Admin approval of listings is unchanged.

## Check it works

1. Sign up with email on your phone. If Brevo is on, you get a confirmation email. Confirm, sign in.
2. Fill in the profile, save a listing. Sign in on another device: both are there.
3. Sign out, then try "Continue with Google".
4. Try "Forgot your password?" and confirm the reset email arrives.
