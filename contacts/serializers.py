from rest_framework import serializers

from contacts.models import Contact, normalize_phone


class ContactSerializer(serializers.ModelSerializer):
    status_name = serializers.ReadOnlyField(source="status.name")

    # Never read from the request body — CurrentUserDefault fills it from the
    # session. It has to be a declared field even so: DRF only builds the
    # UniqueConstraint validators when every field in the constraint is present
    # on the serializer, and both of ours include "owner". Without this, a
    # duplicate reaches the database and surfaces as a 500 instead of a 400.
    owner = serializers.HiddenField(default=serializers.CurrentUserDefault())

    class Meta:
        model = Contact
        fields = [
            "id", "owner", "first_name", "last_name", "phone", "email",
            "city", "status", "status_name", "created_at",
        ]

    def validate_phone(self, value):
        # Normalize before the uniqueness validators run, so the incoming value
        # is compared in the same form it will be stored in.
        return normalize_phone(value)
