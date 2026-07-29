# Supra Contacts

Django + DRF contact manager with per-user data isolation, weather lookup by city, and CSV import.

## Setup

```
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo   # optional: demo1/demo2 users with sample contacts
python manage.py runserver
```

## Verifying data isolation

`seed_demo` creates two users, **demo1** and **demo2** (password `demo12345`),
each with their own contacts in different cities. Log in as one, note a
contact's ID from its detail URL, then either:

- log in as the other user and edit the URL to that ID directly — you'll get
  a 404, not a permission error, because the queryset is filtered by
  `owner=request.user` before the row is ever looked up; or
- hit `/api/contacts/` as each user and confirm the lists don't overlap.

No template hides this — it's enforced at the queryset level everywhere
`Contact` is touched.
