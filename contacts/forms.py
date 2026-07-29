from django import forms
from django.core.exceptions import ValidationError

from contacts.models import (
    Contact,
    DEFAULT_PHONE_REGION,
    normalize_phone,
    phone_region_choices,
    region_for_phone,
    validate_phone_format,
)
from contacts.services import WeatherUnavailable, find_settlements


class ContactForm(forms.ModelForm):
    # Not a model field: the country only tells libphonenumber which numbering
    # plan to assume for numbers typed without a "+" prefix. What gets stored is
    # always E.164, which already encodes the country.
    country = forms.ChoiceField(
        choices=phone_region_choices,
        initial=DEFAULT_PHONE_REGION,
        required=False,
        label="Country",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    # Declared explicitly to drop the model field's validator, which would run
    # against the default region before we know which country the user picked.
    phone = forms.CharField(
        max_length=20,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )

    field_order = ["first_name", "last_name", "country", "phone", "email", "city", "status"]

    class Meta:
        model = Contact
        fields = ["first_name", "last_name", "phone", "email", "city", "status"]
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "form-control"}),
            "last_name": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "city": forms.TextInput(attrs={"class": "form-control"}),
            "status": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, owner=None, check_city=True, **kwargs):
        self.owner = owner
        # CSV import turns this off: one geocode request per row would be both
        # unusably slow and a good way to get rate-limited by Nominatim.
        self.check_city = check_city
        self.city_candidates = []
        super().__init__(*args, **kwargs)
        # When editing, pre-select the country the stored number belongs to.
        if self.instance.pk and not self.is_bound:
            self.fields["country"].initial = region_for_phone(self.instance.phone)

    def clean_email(self):
        value = self.cleaned_data["email"]
        if self._duplicate_exists(email=value):
            raise ValidationError("You already have a contact with this email address.")
        return value

    def clean(self):
        # Phone is handled here rather than in clean_phone() because it depends
        # on the country field, and per-field cleaning order isn't guaranteed.
        cleaned = super().clean()
        phone = cleaned.get("phone")
        if not phone:
            return cleaned

        region = cleaned.get("country") or DEFAULT_PHONE_REGION
        try:
            validate_phone_format(phone, region)
        except ValidationError as exc:
            self.add_error("phone", exc)
            return cleaned

        normalized = normalize_phone(phone, region)
        if self._duplicate_exists(phone=normalized):
            self.add_error("phone", "You already have a contact with this phone number.")
        else:
            cleaned["phone"] = normalized

        self._resolve_city(cleaned)
        return cleaned

    def _resolve_city(self, cleaned):
        """Ask the user which place they meant, when the name is ambiguous.

        Resolving this at write time means the stored city is unambiguous, so
        the weather lookup never has to guess again on the read path.
        """
        city = (cleaned.get("city") or "").strip()
        if not city or not self.check_city:
            return

        # The user already answered the question on the previous submit.
        picked = (self.data.get("city_choice") or "").strip()
        if picked:
            cleaned["city"] = picked
            return

        # Editing without touching the city shouldn't re-open a settled question.
        if self.instance.pk and self.instance.city == city:
            return

        try:
            candidates = find_settlements(city)
        except WeatherUnavailable:
            # A dead geocoder must never stop someone saving a contact.
            return

        # One match, or the user typed a label we already offered: nothing to ask.
        if len(candidates) < 2 or city in candidates:
            return

        self.city_candidates = candidates
        self.add_error("city", "Several places share this name — pick the one you meant.")

    def _duplicate_exists(self, **lookup):
        """Per-owner uniqueness check, excluding the row being edited."""
        qs = Contact.objects.filter(owner=self.owner, **lookup)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        return qs.exists()


class CsvImportForm(forms.Form):
    file = forms.FileField(widget=forms.ClearableFileInput(attrs={"class": "form-control"}))
