import io

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from contacts.models import Contact, ContactStatus


class ContactViewsTests(TestCase):
    def setUp(self):
        self.new_status = ContactStatus.objects.get(slug="new")
        self.alice = User.objects.create_user("alice", password="x")
        self.bob = User.objects.create_user("bob", password="x")
        self.alice_contact = Contact.objects.create(
            owner=self.alice, first_name="Anna", last_name="Owner",
            phone="+48111111111", email="anna@x.com", city="Warsaw", status=self.new_status,
        )

    def test_list_requires_login(self):
        resp = self.client.get(reverse("contact-list"))
        self.assertEqual(resp.status_code, 302)

    def test_list_shows_only_own_contacts(self):
        self.client.force_login(self.bob)
        resp = self.client.get(reverse("contact-list"))
        self.assertEqual(list(resp.context["contacts"]), [])

    def test_edit_and_delete_other_users_contact_is_404(self):
        self.client.force_login(self.bob)
        edit_url = reverse("contact-update", args=[self.alice_contact.pk])
        delete_url = reverse("contact-delete", args=[self.alice_contact.pk])
        self.assertEqual(self.client.get(edit_url).status_code, 404)
        self.assertEqual(self.client.post(delete_url).status_code, 404)

    def test_duplicate_phone_shows_validation_error_not_500(self):
        self.client.force_login(self.alice)
        resp = self.client.post(reverse("contact-create"), {
            "first_name": "Dup", "last_name": "Phone",
            "phone": "+48 111-111-111", "email": "dup@x.com",
            "city": "Warsaw", "status": self.new_status.id,
        })
        self.assertEqual(resp.status_code, 200)  # re-renders form, no crash
        self.assertIn("phone", resp.context["form"].errors)

    def test_csv_import_skips_bad_rows_and_dedupes(self):
        self.client.force_login(self.alice)
        csv_bytes = (
            "﻿first_name,last_name,phone,email,city,status\r\n"
            "New,Person,+48222222222,new.person@x.com,Krakow,new\r\n"
            "Bad,Phone,notaphone,bad@x.com,Krakow,new\r\n"
            "Dup,Existing,+48111111111,other@x.com,Warsaw,new\r\n"
        ).encode("utf-8")
        upload = io.BytesIO(csv_bytes)
        upload.name = "contacts.csv"
        resp = self.client.post(reverse("contact-import"), {"file": upload}, follow=True)
        messages = [str(m) for m in resp.context["messages"]]
        self.assertIn("1 imported, 2 skipped.", messages)
        self.assertTrue(Contact.objects.filter(email="new.person@x.com").exists())
        self.assertFalse(Contact.objects.filter(email="bad@x.com").exists())
        self.assertFalse(Contact.objects.filter(email="other@x.com").exists())
