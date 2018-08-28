# -*- coding: utf-8 -*-
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    UpdateView,
    ListView
)

from .models import (
	ChangeLog,
)


class ChangeLogCreateView(CreateView):

    model = ChangeLog


class ChangeLogDeleteView(DeleteView):

    model = ChangeLog


class ChangeLogDetailView(DetailView):

    model = ChangeLog


class ChangeLogUpdateView(UpdateView):

    model = ChangeLog


class ChangeLogListView(ListView):

    model = ChangeLog

