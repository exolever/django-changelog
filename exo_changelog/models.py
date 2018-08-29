# -*- coding: utf-8 -*-
from django.utils.encoding import python_2_unicode_compatible
from django.utils.timezone import now
from django.db import models


@python_2_unicode_compatible
class ChangeLog(models.Model):
    app = models.CharField(max_length=255)
    name = models.CharField(max_length=255)
    applied = models.DateTimeField(default=now)

    def __str__(self):
        return "Change %s for %s" % (self.name, self.app)
