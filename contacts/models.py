import re

from django.conf import settings
from django.db import models


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
    phone = models.CharField(max_length=20)
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
        # Strip whitespace/dashes/parens so "+48 123-456 (789)" and
        # "+48123456789" collide under the per-owner unique constraint.
        # "+" isn't in the stripped set, so a leading one survives untouched.
        self.phone = re.sub(r"[\s\-()]", "", self.phone)
        super().save(*args, **kwargs)
