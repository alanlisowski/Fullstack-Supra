# Supra Contacts

A contact manager with per-user data isolation, weather-by-city lookup, and CSV import.

**Stack:** Django 5 + Django REST Framework, Bootstrap 5 (CDN, no build step), SQLite, vanilla JS.

## Setup

```
git clone <repo-url>
cd Fullstack-Supra
python -m venv .venv
.venv/Scripts/activate        # Windows; use `source .venv/bin/activate` on macOS/Linux
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo    # optional: demo1/demo2 users with sample contacts
python manage.py runserver
```

Visit http://127.0.0.1:8000/.

## Demo credentials

`seed_demo` creates two users, each with a handful of contacts in different cities:

- **demo1** / `demo12345`
- **demo2** / `demo12345`

Log in as one, then log in as the other in a different browser (or session) to see that
neither can view or edit the other's contacts — see "Data isolation" below.

## API endpoints

All endpoints require a logged-in session (`SessionAuthentication`).

| Method | Path | Description |
|---|---|---|
| GET | `/api/contacts/` | List the caller's own contacts. Supports `?search=` (matches first/last name, email, city) and `?ordering=` (`last_name`, `-last_name`, `created_at`, `-created_at`) |
| POST | `/api/contacts/` | Create a contact, owned by the caller |
| GET | `/api/contacts/{id}/` | Retrieve one of the caller's contacts (404 for anyone else's) |
| PUT | `/api/contacts/{id}/` | Replace a contact |
| PATCH | `/api/contacts/{id}/` | Partially update a contact |
| DELETE | `/api/contacts/{id}/` | Delete a contact |
| GET | `/api/weather/?city=` | Current weather for a city. 404 if the city can't be resolved, 503 if the weather/geocoding service is down |

The UI (contact list, add/edit/delete, CSV import) is served at `/`, and login/logout at
`/login/` and `/logout/`.

## Design notes

**Weather cache is two layers, to minimize outbound requests.** Geocoding (city name →
lat/lon) is cached for 7 days — coordinates don't move. The forecast (lat/lon → conditions)
is cached separately for 30 minutes, since weather actually changes. On top of that, the
contact list's JS collects the *distinct* cities from the page before fetching, so 25
contacts spread across 5 cities cost 5 requests to `/api/weather/`, not 25 — and repeat
page loads within the cache window cost close to nothing.

**Uniqueness (`email`, `phone`) is enforced per-owner, not globally.** Data isolation
means two different users can legitimately have overlapping contacts — the same client
calling both of two different brokers. A global unique constraint would let user B's
signup fail because user A already has that email in *their* book, which leaks the
existence of another user's data and is simply wrong. `UniqueConstraint(fields=["owner",
"email"])` (and the same for phone) scopes the check to where it belongs.

**Sorting is restricted to an allow-list**, not passed straight into `.order_by()`.
Forwarding an arbitrary `?ordering=` value into the ORM is an easy way to 500 on a bad
field name or leak schema details in the error. `{"last_name", "-last_name", "created_at",
"-created_at"}` is shared between the API view and the UI list view, so invalid input just
falls back to the default ordering in both places instead of crashing.

## CSV import

Upload a CSV via "Import CSV" on the contact list. Expected header:

```
first_name,last_name,phone,email,city,status
```

Sample row:

```
Anna,Kowalska,+48111111111,anna.kowalska@example.com,Warszawa,new
```

`status` is matched against a `ContactStatus` name or slug, case-insensitively, and falls
back to `new` if nothing matches. Rows that are malformed or duplicate an existing contact
(by the same per-owner email/phone rule as above) are skipped, not fatal — the import
reports a summary like "12 imported, 3 skipped" with a reason for each skipped row.

## Running the tests

```
python manage.py test
```

Tests run fully offline — network calls to Nominatim/Open-Meteo are mocked. Test modules
are split by concern: `contacts/test_services.py` (geocoding/weather caching),
`contacts/test_api.py` (REST API), `contacts/test_views.py` (UI views, forms, CSV import).
