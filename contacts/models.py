import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

PHONE_PATTERN = re.compile(r"\+?\d{9,15}")


def normalize_phone(value: str) -> str:
    """Strip separators so "+48 123-456 (789)" and "+48123456789" are one number.

    Shared by Contact.save() and the serializer/form validators: uniqueness has
    to be checked against the same normalized form that gets stored, otherwise
    validation passes and the database constraint fails with a 500.
    """
    return re.sub(r"[\s\-()]", "", value or "")


def validate_phone_format(value: str) -> None:
    """Require 9-15 digits with an optional leading "+".

    Normalizes first so this holds whether it receives raw user input or an
    already-stripped number — DRF runs field validators before validate_phone(),
    so a formatted "+48 123 456 789" arrives here with its spaces intact.
    """
    if not PHONE_PATTERN.fullmatch(normalize_phone(value)):
        raise ValidationError(
            "Enter 9 to 15 digits, optionally prefixed with '+'.",
            code="invalid_phone",
        )


class ContactStatus(models.Model):
    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(unique=True)

    class Meta:
        verbose_name_plural = "contact statuses"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Contact(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="contacts",
    )
    first_name = models.CharField(max_length=80)
    last_name = models.CharField(max_length=80)
    phone = models.CharField(max_length=20, validators=[validate_phone_format])
    email = models.EmailField()
    city = models.CharField(max_length=100)
    status = models.ForeignKey(
        ContactStatus,
        on_delete=models.PROTECT,
        related_name="contacts",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "email"], name="unique_email_per_owner"
            ),
            models.UniqueConstraint(
                fields=["owner", "phone"], name="unique_phone_per_owner"
            ),
        ]

    def __str__(self):
        return self.full_name

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    def save(self, *args, **kwargs):
        # Last line of defence: bulk_create() and .update() bypass save(), so
        # callers that skip it must normalize themselves.
        self.phone = normalize_phone(self.phone)
        super().save(*args, **kwargs)
