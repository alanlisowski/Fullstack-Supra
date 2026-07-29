from django.db import migrations

STATUSES = [
    ("new", "new"),
    ("in progress", "in-progress"),
    ("lost", "lost"),
    ("outdated", "outdated"),
]


def seed_statuses(apps, schema_editor):
    ContactStatus = apps.get_model("contacts", "ContactStatus")
    for name, slug in STATUSES:
        ContactStatus.objects.create(name=name, slug=slug)


def unseed_statuses(apps, schema_editor):
    ContactStatus = apps.get_model("contacts", "ContactStatus")
    ContactStatus.objects.filter(slug__in=[slug for _, slug in STATUSES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("contacts", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_statuses, unseed_statuses),
    ]
