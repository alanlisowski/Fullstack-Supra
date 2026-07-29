# Supra Contacts

A contact manager with per-user data isolation, weather-by-city lookup, and CSV import.

**Stack:** Django 5 + Django REST Framework, Bootstrap 5 (CDN, no build step), SQLite,
vanilla JS, `phonenumbers` (Google's libphonenumber) for phone normalisation.

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

**Phone numbers are stored in E.164, normalised with `phonenumbers`.** `111111111`,
`+48 111-111-111` and `(+48) 111 111 111` are the same number, and per-owner uniqueness is
only meaningful if the database agrees. The library canonicalises all three to
`+48111111111`. Validation uses `is_possible_number()` rather than `is_valid_number()` —
the former checks length against a country's numbering plan, the latter additionally
requires an allocated range, which would reject every test and demo number.

The contact form has a **country selector** feeding the parser's default region, so a UK
number typed locally as `07911123456` is stored as `+447911123456`. Country is not a model
field: E.164 already encodes it, and storing it twice invites the two copies to disagree.
Numbers submitted to the REST API are parsed as Polish unless they carry a `+` prefix.

**"City not found" and "weather service down" are different answers.** Both used to
return `None`, so the user saw one message for two unrelated problems. They are now
separate exceptions mapping to different statuses: `CityNotFound` → **404** (a typo the
user can fix, cached for an hour) and `WeatherUnavailable` → **503** (an outage they can
do nothing about, never cached — otherwise a brief network blip would suppress a city for
the full cache window).

**Geocoding is limited to settlements, and shows what it matched.** Nominatim searches
every OSM feature by default: "Londo" returned a *river* in the DR Congo along with its
very plausible-looking weather. `featureType=settlement` restricts results to towns and
villages. Because that still leaves genuine name collisions, the weather cell also prints
the resolved place ("Warszawa, Polska") underneath — silently wrong data is worse than a
visible error, because users believe it.

**Ambiguous city names are resolved once, at write time.** If a name matches several
settlements, the form asks which was meant and stores the qualified label. The read path
then never has to guess. CSV import skips this check — one geocode request per row would
be slow and would breach Nominatim's rate limit — and a geocoder outage never blocks a
save, since a nice-to-have lookup must not break a core write.

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

`sample_contacts.csv` in the repository root is a ready-made example: two valid rows, one
duplicate, one malformed phone and one missing email. Importing it as `demo1` reports
"2 imported, 3 skipped" and demonstrates the per-row error handling.

Files are read with `utf-8-sig` — Excel writes a BOM that would otherwise corrupt the
first column header. Phone numbers are normalised on import like anywhere else, so
`+48 501 502 503` in the file is stored as `+48501502503`.

## Running the tests

```
python manage.py test
```

Tests run fully offline — network calls to Nominatim/Open-Meteo are mocked. Test modules
are split by concern: `contacts/test_services.py` (geocoding, caching, the two failure
modes), `contacts/test_api.py` (REST API, authentication, isolation, the ordering
allow-list), `contacts/test_views.py` (UI views, form validation, CSV import).

## Known limitations

`LocMemCache` is per-process. Under the development server that's a single process, so
the TTLs behave as documented; in a multi-worker deployment each worker would hold its
own copy and Redis would be the right backend. That's a `CACHES` setting change only —
no application code depends on the backend.

`city` is free text rather than a related model. A dedicated location table with stored
coordinates would remove geocoding from the read path entirely, but at this scale it adds
migrations and a CSV column for little gain; resolving ambiguity at write time addresses
the same problem more cheaply.

Client-side validation is deliberately looser than the server's. The browser catches
obvious typos immediately, but the server is the authority — a stricter frontend would
reject numbers the API accepts, which is the worse failure.
