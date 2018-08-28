# -*- coding: utf-8 -*-
from django.conf.urls import url
from django.views.generic import TemplateView

from . import views


app_name = 'exo_changelog'
urlpatterns = [
    url(
        regex="^ChangeLog/~create/$",
        view=views.ChangeLogCreateView.as_view(),
        name='ChangeLog_create',
    ),
    url(
        regex="^ChangeLog/(?P<pk>\d+)/~delete/$",
        view=views.ChangeLogDeleteView.as_view(),
        name='ChangeLog_delete',
    ),
    url(
        regex="^ChangeLog/(?P<pk>\d+)/$",
        view=views.ChangeLogDetailView.as_view(),
        name='ChangeLog_detail',
    ),
    url(
        regex="^ChangeLog/(?P<pk>\d+)/~update/$",
        view=views.ChangeLogUpdateView.as_view(),
        name='ChangeLog_update',
    ),
    url(
        regex="^ChangeLog/$",
        view=views.ChangeLogListView.as_view(),
        name='ChangeLog_list',
    ),
	]
