from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework.test import APITestCase

from contacts.models import Contact, ContactStatus


class ContactApiTests(APITestCase):
    def setUp(self):
        self.status = ContactStatus.objects.create(name="Lead", slug="lead")
        self.alice = User.objects.create_user("alice", password="x")
        self.bob = User.objects.create_user("bob", password="x")
        self.alice_contact = Contact.objects.create(
            owner=self.alice, first_name="A", last_name="Owner",
            phone="+48111111111", email="a@x.com", city="Warsaw", status=self.status,
        )

    def test_requires_authentication(self):
        resp = self.client.get(reverse("contact-api-list"))
        self.assertEqual(resp.status_code, 403)

    def test_owner_cannot_see_or_modify_others_contact(self):
        self.client.force_login(self.bob)
        list_resp = self.client.get(reverse("contact-api-list"))
        self.assertEqual(list_resp.json(), [])

        detail_url = reverse("contact-api-detail", args=[self.alice_contact.id])
        self.assertEqual(self.client.get(detail_url).status_code, 404)
        self.assertEqual(self.client.delete(detail_url).status_code, 404)
        self.assertEqual(Contact.objects.filter(id=self.alice_contact.id).exists(), True)

    def test_create_sets_owner_from_request_not_payload(self):
        self.client.force_login(self.bob)
        resp = self.client.post(reverse("contact-api-list"), {
            "first_name": "B", "last_name": "New", "phone": "+48222222222",
            "email": "b@x.com", "city": "Krakow", "status": self.status.id,
        })
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(Contact.objects.get(email="b@x.com").owner, self.bob)

    def test_ordering_rejects_unknown_field(self):
        self.client.force_login(self.alice)
        resp = self.client.get(reverse("contact-api-list"), {"ordering": "email"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 1)  # falls back to default, doesn't 500

    def test_search_matches_city(self):
        self.client.force_login(self.alice)
        resp = self.client.get(reverse("contact-api-list"), {"search": "warsaw"})
        self.assertEqual(len(resp.json()), 1)
        resp = self.client.get(reverse("contact-api-list"), {"search": "nowhere"})
        self.assertEqual(resp.json(), [])
