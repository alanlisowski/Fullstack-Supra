# Supra Brokers — Fullstack Task: Build Plan & Claude Code Prompts

Stack decided: **Django + DRF + Bootstrap 5 (CDN) + SQLite**, bonus tasks = **caching, tests, login/data isolation**.

---

## Target structure

```
.
├── manage.py
├── requirements.txt
├── .gitignore
├── README.md
├── config/                     # project package
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
└── contacts/                   # single app — everything lives here
    ├── models.py               # ContactStatus, Contact
    ├── forms.py                # ContactForm, CsvImportForm
    ├── serializers.py          # DRF serializer
    ├── api.py                  # DRF ViewSet + weather endpoint
    ├── views.py                # class-based views for the UI
    ├── services.py             # geocoding + weather + caching
    ├── admin.py
    ├── urls.py
    ├── tests.py
    ├── migrations/
    │   ├── 0001_initial.py
    │   └── 0002_seed_statuses.py   # data migration, not fixtures
    ├── templates/contacts/
    └── static/contacts/
```

One app, ~9 Python files. Nothing is split until it needs to be.

---

## Design decisions worth defending in the interview

The PDF says *"Zastanów się jak ograniczyć ilość requestów do obu API"* — that sentence is the real test. Here's the answer:

**1. Two-layer cache, keyed by city — not by contact.**
50 contacts in Warszawa should cost **one** API call, not 50.
- Geocode cache (city → lat/lon): TTL **7 days**. Coordinates don't move.
- Weather cache (lat/lon → conditions): TTL **30 min**.

**2. Lazy-load weather via AJAX, deduped client-side.**
The list page renders instantly with placeholders. JS collects *distinct* cities from the table, fires one request per unique city against our own `/api/weather/?city=X`. That endpoint hits the cache. Result: fast first paint *and* minimal upstream calls — you get credit for both the frontend and backend approaches the PDF offers.

**3. Nominatim requires a `User-Agent` header.** Without it you get 403s. This is the #1 thing people miss on this task.

**4. Statuses seeded via data migration**, so a fresh `migrate` gives a working app — no manual fixture loading step in the README.

**5. Sorting uses an allow-list** (`{"last_name", "-last_name", "created_at", "-created_at"}`). Passing raw GET params into `.order_by()` is a 500-error waiting to happen.

**6. Uniqueness is per-owner**, via `UniqueConstraint(fields=["owner", "email"])`, not a global `unique=True`. Since the bonus task adds per-user data isolation, two different users must be able to hold the same contact. Note this decision in the README — it shows you thought about the interaction between two requirements instead of applying each blindly.

**7. Phone is normalized before saving** (strip spaces, dashes, parens). Otherwise `+48 123 456 789` and `+48123456789` both slip past the unique constraint.

---

## The prompts

Run `claude` inside `C:\Projects\Fullstack Supra`, then paste these **one at a time**. Verify each step works before moving on.

---

### Prompt 1 — Scaffold + models

```
Create a Django 5 project for a contact management app. Use SQLite. Structure:

- Project package named `config` (settings.py, urls.py, wsgi.py) at the repo root
- A single app named `contacts`

In contacts/models.py define two models, with all names/comments in English:

1. ContactStatus
   - name: CharField(max_length=50, unique=True)
   - slug: SlugField(unique=True)
   - __str__ returns name
   - Meta: verbose_name_plural = "contact statuses", ordering by name

2. Contact
   - owner: FK to settings.AUTH_USER_MODEL, on_delete=CASCADE, related_name="contacts"
   - first_name, last_name: CharField(max_length=80)
   - phone: CharField(max_length=20)
   - email: EmailField()
   - city: CharField(max_length=100)
   - status: FK to ContactStatus, on_delete=PROTECT, related_name="contacts"
   - created_at: DateTimeField(auto_now_add=True)
   - Meta.ordering = ["-created_at"]
   - Meta.constraints: UniqueConstraint on (owner, email) and on (owner, phone),
     with clear names like "unique_email_per_owner"
   - Override save() to normalize phone: strip all whitespace, dashes, parens
     before saving. Keep a leading "+" if present.
   - full_name property returning "first_name last_name"

Add a data migration 0002_seed_statuses.py that creates four statuses:
"new", "in progress", "lost", "outdated" (with matching slugs). Make it
reversible with a proper reverse function.

Register both models in admin.py with sensible list_display and list_filter.

Also create requirements.txt (django, djangorestframework, requests) and a
Python .gitignore that excludes db.sqlite3, __pycache__, .venv, .env.

Then run makemigrations and migrate to prove it works.
```

**Verify:** `python manage.py migrate` runs clean, `python manage.py shell -c "from contacts.models import ContactStatus; print(ContactStatus.objects.count())"` prints `4`.

---

### Prompt 2 — Weather service with caching

```
Create contacts/services.py — the weather layer. This is the part the task
brief specifically asks us to think about, so optimize request count.

Two functions plus one public entry point:

1. geocode_city(city: str) -> tuple[float, float] | None
   - Calls https://nominatim.openstreetmap.org/search
     with params q=city, format=json, limit=1
   - MUST send a User-Agent header (e.g. "supra-contacts/1.0") — Nominatim
     returns 403 without one. Add a comment explaining why.
   - Caches the result under key f"geo:{normalized_city}" for 7 days.
     Coordinates never change, so a long TTL is safe.
   - Cache negative results too (as a sentinel), shorter TTL (1 hour), so a
     typo'd city doesn't hammer the API on every page load.

2. fetch_weather(lat, lon) -> dict | None
   - Calls https://api.open-meteo.com/v1/forecast with
     latitude, longitude, current_weather=true
   - Returns {"temperature": ..., "humidity": ..., "windspeed": ...}
   - Open-Meteo's current_weather block has no humidity, so also request
     hourly=relative_humidity_2m and read the value matching the current
     hour returned in current_weather.time. Comment this clearly.

3. get_city_weather(city: str) -> dict | None
   - Public entry point. Normalizes the city name (strip + casefold) for the
     cache key so "warszawa" and "Warszawa " share one entry.
   - Caches the final result for 30 minutes under f"weather:{normalized_city}".
   - Chains geocode -> fetch. Returns None if either fails.

Requirements:
- Use requests with timeout=5 on every call. Never let a slow API hang a page.
- Wrap network calls in try/except requests.RequestException, log a warning,
  return None. A dead weather API must never 500 the contact list.
- Use django.core.cache.cache. Configure LocMemCache in settings.py.
- Put TTLs in module-level named constants, not magic numbers inline.

Keep it under ~90 lines. No classes — plain functions are enough here.
```

**Verify:** `python manage.py shell -c "from contacts.services import get_city_weather; print(get_city_weather('Warszawa'))"` returns a dict.

---

### Prompt 3 — DRF API

```
Add the REST API using Django REST Framework.

contacts/serializers.py:
- ContactSerializer with fields: id, first_name, last_name, phone, email,
  city, status, status_name, created_at
- status is the writable FK (PrimaryKeyRelatedField); status_name is a
  read-only source="status.name" so clients get a label without a second call
- owner is NOT exposed — it's set server-side from request.user

contacts/api.py:
- ContactViewSet(ModelViewSet) giving GET/POST/PUT/PATCH/DELETE on
  /api/contacts/ and /api/contacts/{id}/
- permission_classes = [IsAuthenticated]
- get_queryset returns Contact.objects.filter(owner=self.request.user)
  .select_related("status") — this is what enforces data isolation, so a
  user physically cannot PUT or DELETE another user's contact (they get 404)
- perform_create sets owner=self.request.user
- Add filtering: ?search= (matches first_name, last_name, email, city) and
  ?ordering= restricted to an allow-list of
  {last_name, -last_name, created_at, -created_at}. Reject anything else by
  falling back to the default ordering — never pass raw input to order_by.

- Also add a small function-based view `city_weather` (@api_view(["GET"]))
  at /api/weather/?city=X that returns get_city_weather(city) as JSON,
  404 if the city can't be resolved. The frontend will call this.

Wire a DefaultRouter in contacts/urls.py and include it under /api/ in
config/urls.py. Add REST_FRAMEWORK settings to settings.py with
DEFAULT_AUTHENTICATION_CLASSES = SessionAuthentication.

Keep the viewset under 40 lines — DRF should be doing the work, not us.
```

**Verify:** `curl` or browser at `/api/contacts/` returns 403 when logged out, JSON list when logged in.

---

### Prompt 4 — Auth + data isolation

```
Add authentication. Login only — no registration, per the task brief.

- Use Django's built-in LoginView and LogoutView in config/urls.py, with a
  custom template at contacts/templates/registration/login.html
- settings.py: LOGIN_REDIRECT_URL = "contact-list", LOGOUT_REDIRECT_URL = "login",
  LOGIN_URL = "login"
- Every UI view must use LoginRequiredMixin
- Add a management command `seed_demo` in contacts/management/commands/ that
  creates two demo users (demo1/demo2, password "demo12345") each with 3-4
  contacts in different cities. This lets a reviewer verify isolation in
  10 seconds without touching the shell — call that out in the README.

Isolation rule, applied everywhere without exception: every queryset touching
Contact filters on owner=self.request.user. Never rely on a template hiding a
button — a user must get a 404 if they type another user's contact ID into the
URL directly.
```

**Verify:** log in as demo1, note a contact ID from demo2's set, hit `/contacts/<that-id>/edit/` → 404.

---

### Prompt 5 — UI: list, search, sort, CRUD, CSV import

```
Build the UI with Bootstrap 5 from CDN (no build step, no npm).

Templates in contacts/templates/contacts/:
- base.html — Bootstrap 5 CDN link, navbar with app name, username, logout
  link, and a {% block content %}
- contact_list.html — responsive table: Name, Phone, Email, City, Status
  (as a colored badge), Added date, Weather column, Actions (edit/delete).
  Above the table: a search input, sort dropdown, "Add contact",
  "Import CSV" buttons. Include Django pagination controls (25 per page).
- contact_form.html — shared by create and update
- contact_confirm_delete.html
- contact_import.html — file upload form

contacts/views.py — class-based views, all with LoginRequiredMixin:
- ContactListView(ListView): paginate_by=25, get_queryset filters by owner,
  applies ?search= (icontains across first_name, last_name, email, city) and
  ?sort= from the SAME allow-list used in the API. select_related("status").
- ContactCreateView, ContactUpdateView, ContactDeleteView (owner-filtered
  querysets, success_url back to the list)
- contact_import — handles CSV upload

contacts/forms.py:
- ContactForm (ModelForm) with Bootstrap "form-control" widget attrs.
  Add clean_email/clean_phone that check per-owner uniqueness and raise a
  readable ValidationError instead of leaking an IntegrityError.
- CsvImportForm with a single FileField

CSV import behaviour:
- Expected header: first_name,last_name,phone,email,city,status
- Use csv.DictReader with io.TextIOWrapper(encoding="utf-8-sig") — the BOM
  will corrupt your first column header if you skip this, and Excel writes one
- Match status by name OR slug, case-insensitive; fall back to "new"
- Wrap the whole import in transaction.atomic()
- Skip (don't crash on) rows that are duplicates or fail validation; collect
  errors and show the user a summary: "12 imported, 3 skipped" with reasons
  via django.contrib.messages

contacts/static/contacts/app.js — vanilla JS, no jQuery:
1. Client-side form validation on the contact form: email regex, phone must be
   9-15 digits allowing +, spaces, dashes. Show Bootstrap .is-invalid classes
   and .invalid-feedback text. Block submit while invalid.
2. Weather loading: read data-city off each table row, build a Set of DISTINCT
   cities, fire one fetch() per unique city to /api/weather/?city=,
   then fill every row sharing that city. Show a spinner placeholder while
   loading and an em-dash on failure. Add a comment noting the dedupe is what
   keeps a 25-row page down to a handful of API calls.

Keep templates clean — no inline <style>, no inline onclick handlers.
```

**Verify:** add a contact, search for it, sort by name, import a CSV, watch the weather column populate. Open DevTools Network tab and confirm you see one `/api/weather/` call per distinct city, not per row.

---

### Prompt 6 — Tests

```
Write focused unit tests in contacts/tests.py. Quality over quantity — three
tests that prove the non-obvious parts work:

1. WeatherCacheTest — patch contacts.services.requests.get. Call
   get_city_weather("Warszawa") twice. Assert the mock was called only for the
   first invocation (cache hit on the second). This proves the optimization the
   task brief explicitly asks about. Remember to clear the cache in setUp.

2. ApiIsolationTest — create two users each with one contact. Log in as user A.
   Assert GET /api/contacts/ returns only A's contact; assert
   DELETE /api/contacts/{B's id}/ returns 404 and B's contact still exists.

3. CsvImportTest — post a small in-memory CSV containing one valid row, one
   duplicate, and one malformed row. Assert only the valid row was created and
   that the response reports the skipped rows rather than raising.

Use django.test.TestCase and Client. Use override_settings for the cache
backend if needed. All tests must pass offline — no real network calls.
```

**Verify:** `python manage.py test` → all green, and it works with wifi off.

---

### Prompt 7 — README + final polish

```
Write README.md covering:
- Short project description and the stack used
- Setup: clone, venv, pip install -r requirements.txt, migrate, seed_demo,
  runserver — as copy-pasteable commands that work start to finish
- Demo credentials (demo1 / demo12345)
- API endpoint table: method, path, description
- A short "Design notes" section explaining, briefly:
  * the two-layer weather cache (7d geocode / 30min weather) and the
    client-side city dedupe — i.e. how we minimized API requests
  * why uniqueness is per-owner rather than global, given the data isolation
    requirement
  * why sorting uses an allow-list
- CSV import format with a sample row
- How to run the tests

Then do a cleanup pass over the whole project:
- Remove unused imports and any dead code
- Confirm every comment explains WHY, not WHAT — delete the obvious ones
- Confirm no secrets are committed; SECRET_KEY reads from env with a dev fallback
- Confirm DEBUG reads from env
- Run `python manage.py check` and the test suite one final time
```

Then, still in Claude Code, run the built-in commands:

```
/security-review
```

It catches the things reviewers grep for first — hardcoded `SECRET_KEY`, `DEBUG=True`, missing CSRF, over-permissive querysets.

---

## Suggested schedule

You have 7 days. This is roughly 6–9 hours of actual work.

| Session | Prompts | Outcome |
|---|---|---|
| 1 | 1–2 | Models migrate, weather service returns live data |
| 2 | 3–4 | API responds, login works, isolation verified |
| 3 | 5 | Full UI working end to end |
| 4 | 6–7 | Tests green, README done, security pass |

Leave a day of buffer. Ship it on day 5 or 6, not day 7.

---

## Before you submit

- [ ] Fresh clone into a new folder → follow your own README exactly → app runs. Do this for real; it's the single most common failure.
- [ ] `python manage.py test` passes
- [ ] `db.sqlite3` and `__pycache__` are NOT committed
- [ ] Every variable, class, and comment is in English (explicit requirement in the brief)
- [ ] You can explain every line — expect them to ask about the caching strategy specifically
