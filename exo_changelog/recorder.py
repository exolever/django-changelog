from __future__ import unicode_literals

from django.db.utils import DatabaseError
from django.db import DEFAULT_DB_ALIAS, connections

from .exceptions import ChangeSchemaMissing
from .models import ChangeLog


class ChangeRecorder(object):
    """
    Deals with storing changes records in the database.

    Because this table is actually itself used for dealing with model
    creation, it's the one thing we can't do normally via changes.
    We manually handle table creation/schema updating (using schema backend)
    and then have a floating model to do queries with.

    If a change is unapplied its row is removed from the table. Having
    a row in the table always means a change is applied.
    """

    def __init__(self, connection):
        if not connection:
            self.connection = connections[DEFAULT_DB_ALIAS]
        else:
            self.connection = connection

    @property
    def change_qs(self):
        return ChangeLog.objects.using(self.connection.alias)

    def ensure_schema(self):
        """
        Ensures the table exists and has the correct schema.
        """
        # If the table's there, that's fine - we've never changed its schema
        # in the codebase.
        if ChangeLog._meta.db_table in self.connection.introspection.table_names(self.connection.cursor()):
            return
        # Make the table
        try:
            with self.connection.schema_editor() as editor:
                editor.create_model(self.Migration)
        except DatabaseError as exc:
            raise ChangeSchemaMissing('Unable to create the changelog_change table (%s)' % exc)

    def applied_changes(self):
        """
        Returns a set of (app, name) of applied changes.
        """
        self.ensure_schema()
        return {tuple(x) for x in self.change_qs.values_list('app', 'name')}

    def record_applied(self, app, name):
        """
        Records that a change was applied.
        """
        self.ensure_schema()
        self.change_qs.create(app=app, name=name)

    def record_unapplied(self, app, name):
        """
        Records that a change was unapplied.
        """
        self.ensure_schema()
        self.change_qs.filter(app=app, name=name).delete()

    def flush(self):
        """
        Deletes all change records. Useful if you're testing changes.
        """
        self.change_qs.all().delete()
