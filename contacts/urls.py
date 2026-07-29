from django.urls import path

from contacts import views

urlpatterns = [
    path("", views.ContactListView.as_view(), name="contact-list"),
    path("contacts/add/", views.ContactCreateView.as_view(), name="contact-create"),
    path("contacts/<int:pk>/edit/", views.ContactUpdateView.as_view(), name="contact-update"),
    path("contacts/<int:pk>/delete/", views.ContactDeleteView.as_view(), name="contact-delete"),
    path("contacts/import/", views.contact_import, name="contact-import"),
]
