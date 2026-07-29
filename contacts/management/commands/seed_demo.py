from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from contacts.models import Contact, ContactStatus

DEMO_PASSWORD = "demo12345"

# (username, [(first, last, phone, email, city, status_slug), ...])
DEMO_DATA = [
    ("demo1", [
        ("Anna", "Kowalska", "+48111111111", "anna.kowalska@example.com", "Warszawa", "new"),
        ("Piotr", "Nowak", "+48111111112", "piotr.nowak@example.com", "Kraków", "in-progress"),
        ("Ewa", "Wiśniewska", "+48111111113", "ewa.wisniewska@example.com", "Gdańsk", "lost"),
    ]),
    ("demo2", [
        ("John", "Smith", "+441111111111", "john.smith@example.com", "London", "new"),
        ("Maria", "Garcia", "+34611222333", "maria.garcia@example.com", "Madrid", "in-progress"),
        ("Luca", "Rossi", "+393331112223", "luca.rossi@example.com", "Roma", "outdated"),
        ("Sophie", "Dubois", "+33612345678", "sophie.dubois@example.com", "Paris", "new"),
    ]),
]


class Command(BaseCommand):
    help = "Creates demo1/demo2 users (password: demo12345), each with a few contacts, to demo owner isolation."

    def handle(self, *args, **options):
        for username, contacts in DEMO_DATA:
            user, created = User.objects.get_or_create(username=username)
            if created:
                user.set_password(DEMO_PASSWORD)
                user.save()

            for first, last, phone, email, city, status_slug in contacts:
                status = ContactStatus.objects.get(slug=status_slug)
                Contact.objects.get_or_create(
                    owner=user, email=email,
                    defaults=dict(
                        first_name=first, last_name=last, phone=phone,
                        city=city, status=status,
                    ),
                )

        self.stdout.write(self.style.SUCCESS(
            "Seeded demo1 and demo2 (password: demo12345)."
        ))
