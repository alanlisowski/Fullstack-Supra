import csv
import io

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Q
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from contacts.api import ORDERING_ALLOWED
from contacts.forms import ContactForm, CsvImportForm
from contacts.models import Contact, ContactStatus


class ContactListView(LoginRequiredMixin, ListView):
    template_name = "contacts/contact_list.html"
    context_object_name = "contacts"
    paginate_by = 25

    def get_queryset(self):
        qs = Contact.objects.filter(owner=self.request.user).select_related("status")

        search = self.request.GET.get("search")
        if search:
            qs = qs.filter(
                Q(first_name__icontains=search) | Q(last_name__icontains=search)
                | Q(email__icontains=search) | Q(city__icontains=search)
            )

        sort = self.request.GET.get("sort")
        if sort in ORDERING_ALLOWED:
            qs = qs.order_by(sort)

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["search"] = self.request.GET.get("search", "")
        ctx["sort"] = self.request.GET.get("sort", "")
        params = self.request.GET.copy()
        params.pop("page", None)
        ctx["querystring"] = params.urlencode()
        return ctx


class ContactFormMixin:
    form_class = ContactForm
    template_name = "contacts/contact_form.html"
    success_url = reverse_lazy("contact-list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["owner"] = self.request.user
        return kwargs


class ContactCreateView(LoginRequiredMixin, ContactFormMixin, CreateView):
    def form_valid(self, form):
        form.instance.owner = self.request.user
        return super().form_valid(form)


class ContactUpdateView(LoginRequiredMixin, ContactFormMixin, UpdateView):
    def get_queryset(self):
        return Contact.objects.filter(owner=self.request.user)


class ContactDeleteView(LoginRequiredMixin, DeleteView):
    template_name = "contacts/contact_confirm_delete.html"
    success_url = reverse_lazy("contact-list")

    def get_queryset(self):
        return Contact.objects.filter(owner=self.request.user)


def _resolve_status(name_or_slug):
    name_or_slug = (name_or_slug or "").strip()
    status = ContactStatus.objects.filter(
        Q(name__iexact=name_or_slug) | Q(slug__iexact=name_or_slug)
    ).first()
    return status or ContactStatus.objects.filter(slug="new").first()


def _import_rows(rows, owner):
    imported = 0
    errors = []
    with transaction.atomic():
        for line_no, row in enumerate(rows, start=2):  # header is line 1
            status = _resolve_status(row.get("status"))
            form = ContactForm(
                data={
                    "first_name": (row.get("first_name") or "").strip(),
                    "last_name": (row.get("last_name") or "").strip(),
                    "phone": (row.get("phone") or "").strip(),
                    "email": (row.get("email") or "").strip(),
                    "city": (row.get("city") or "").strip(),
                    "status": status.pk if status else "",
                },
                owner=owner,
                # Geocoding every row would be slow and would trip Nominatim's
                # rate limit; imported cities are taken at face value.
                check_city=False,
            )
            if form.is_valid():
                contact = form.save(commit=False)
                contact.owner = owner
                contact.save()
                imported += 1
            else:
                reasons = "; ".join(e[0] for e in form.errors.values())
                errors.append(f"Row {line_no}: {reasons}")
    return imported, errors


@login_required
def contact_import(request):
    if request.method == "POST":
        form = CsvImportForm(request.POST, request.FILES)
        if form.is_valid():
            # utf-8-sig strips a BOM if Excel wrote one; left as plain utf-8
            # it would corrupt the first header ("first_name" -> "﻿first_name").
            reader = csv.DictReader(io.TextIOWrapper(form.cleaned_data["file"], encoding="utf-8-sig"))
            imported, errors = _import_rows(reader, request.user)
            messages.success(request, f"{imported} imported, {len(errors)} skipped.")
            for reason in errors:
                messages.warning(request, reason)
            return redirect("contact-list")
    else:
        form = CsvImportForm()
    return render(request, "contacts/contact_import.html", {"form": form})
