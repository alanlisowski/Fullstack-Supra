import re

import phonenumbers
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

# Numbers typed without a country code are assumed to be Polish. Anything with
# an explicit "+" prefix is parsed against its own country's rules regardless.
DEFAULT_PHONE_REGION = "PL"


# Regions offered in the contact form's country picker. Names are ours; the
# dial codes are read from libphonenumber so the two can never drift apart.
PHONE_REGIONS = [
    "PL", "DE", "GB", "CZ", "SK", "UA", "LT", "NL", "FR", "ES", "IT", "US",
]
REGION_NAMES = {
    "PL": "Poland", "DE": "Germany", "GB": "United Kingdom", "CZ": "Czechia",
    "SK": "Slovakia", "UA": "Ukraine", "LT": "Lithuania", "NL": "Netherlands",
    "FR": "France", "ES": "Spain", "IT": "Italy", "US": "United States",
}


def phone_region_choices():
    """(code, "Poland (+48)") pairs for the form's country select."""
    return [
        (region, f"{REGION_NAMES[region]} (+{phonenumbers.country_code_for_region(region)})")
        for region in PHONE_REGIONS
    ]


def _parse_phone(value: str, region: str = DEFAULT_PHONE_REGION):
    """Return a parsed PhoneNumber, or None if the input can't be one.

    `region` only affects numbers typed without a "+" prefix; an explicit
    country code always wins.
    """
    try:
        parsed = phonenumbers.parse(value or "", region or DEFAULT_PHONE_REGION)
    except phonenumbers.NumberParseException:
        return None
    # is_possible_number checks length against the country's numbering plan.
    # is_valid_number additionally checks the number is in an allocated range,
    # which would reject the fake numbers used in demo data and tests.
    return parsed if phonenumbers.is_possible_number(parsed) else None


def normalize_phone(value: str, region: str = DEFAULT_PHONE_REGION) -> str:
    """Canonicalize to E.164 so one real number has exactly one stored form.

    "111111111", "+48 111-111-111" and "(+48) 111 111 111" all collapse to
    "+48111111111", which is what makes the per-owner unique constraint
    meaningful. Shared by Contact.save(), ContactForm and ContactSerializer:
    uniqueness must be checked against the same form that gets stored, or
    validation passes and the database constraint fails with a 500.

    Unparseable input is returned with separators stripped so that
    validate_phone_format() is the thing that reports the error.
    """
    parsed = _parse_phone(value, region)
    if parsed is None:
        return re.sub(r"[\s\-()]", "", value or "")
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


def region_for_phone(value: str) -> str:
    """Which country a stored number belongs to, for pre-selecting the picker."""
    parsed = _parse_phone(value)
    region = phonenumbers.region_code_for_number(parsed) if parsed else None
    return region if region in REGION_NAMES else DEFAULT_PHONE_REGION


def validate_phone_format(value: str, region: str = DEFAULT_PHONE_REGION) -> None:
    """Reject anything libphonenumber can't read as a phone number."""
    if _parse_phone(value, region) is None:
        raise ValidationError(
            "Enter a valid phone number, e.g. 123 456 789 or +44 7911 123456.",
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
