#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys


def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from contacts.models import Contact, ContactStatus

u = User.objects.create_user("t1", password="x")
s = ContactStatus.objects.first()
c = Contact.objects.create(owner=u, first_name="A", last_name="B",
    phone="+48 123 456 789", email="a@b.pl", city="Warszawa", status=s)

print("normalized phone:", repr(c.phone))   # want '+48123456789'

try:
    with transaction.atomic():
        Contact.objects.create(owner=u, first_name="C", last_name="D",
            phone="+48-123-456-789", email="other@b.pl", city="Kraków", status=s)
    print("FAIL — duplicate phone was accepted")
except IntegrityError:
    print("OK — duplicate phone rejected")