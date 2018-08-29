from django.db.migrations.operations.base import Operation
from django.db import DEFAULT_DB_ALIAS, connections


class RunSQL(Operation):
    """
    Runs some raw SQL. A reverse SQL statement may be provided.

    Also accepts a list of operations that represent the state change effected
    by this SQL change, in case it's custom column/table creation/deletion.
    """
    noop = ''

    def __init__(self, sql, reverse_sql=None, state_operations=None, hints=None, elidable=False):
        self.sql = sql
        self.reverse_sql = reverse_sql
        self.state_operations = state_operations or []
        self.hints = hints or {}
        self.elidable = elidable
        self.connection = connections[DEFAULT_DB_ALIAS]

    def deconstruct(self):
        kwargs = {
            'sql': self.sql,
        }
        if self.reverse_sql is not None:
            kwargs['reverse_sql'] = self.reverse_sql
        if self.state_operations:
            kwargs['state_operations'] = self.state_operations
        if self.hints:
            kwargs['hints'] = self.hints
        return (
            self.__class__.__name__,
            [],
            kwargs
        )

    @property
    def reversible(self):
        return self.reverse_sql is not None

    def state_forwards(self, app_label, state):
        for state_operation in self.state_operations:
            state_operation.state_forwards(app_label, state)

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        self._run_sql(self.sql)

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        if self.reverse_sql is None:
            raise NotImplementedError('You cannot reverse this operation')
        self._run_sql(self.reverse_sql)

    def describe(self):
        return 'Raw SQL operation'

    def _run_sql(self, schema_editor, sqls):
        with self.connection.schema_editor() as schema_editor:
            if isinstance(sqls, (list, tuple)):
                for sql in sqls:
                    params = None
                    if isinstance(sql, (list, tuple)):
                        elements = len(sql)
                        if elements == 2:
                            sql, params = sql
                        else:
                            raise ValueError('Expected a 2-tuple but got %d' % elements)
                    schema_editor.execute(sql, params=params)
            elif sqls != RunSQL.noop:
                statements = schema_editor.connection.ops.prepare_sql_script(sqls)
                for statement in statements:
                    schema_editor.execute(statement, params=None)


class RunPython(Operation):
    """
    Runs Python code in a context suitable for doing versioned ORM operations.
    """

    reduces_to_sql = False

    def __init__(self, code, reverse_code=None, atomic=None, hints=None, elidable=False):
        self.atomic = atomic
        # Forwards code
        if not callable(code):
            raise ValueError('RunPython must be supplied with a callable')
        self.code = code
        # Reverse code
        if reverse_code is None:
            self.reverse_code = None
        else:
            if not callable(reverse_code):
                raise ValueError('RunPython must be supplied with callable arguments')
            self.reverse_code = reverse_code
        self.hints = hints or {}
        self.elidable = elidable

    def deconstruct(self):
        kwargs = {
            'code': self.code,
        }
        if self.reverse_code is not None:
            kwargs['reverse_code'] = self.reverse_code
        if self.atomic is not None:
            kwargs['atomic'] = self.atomic
        if self.hints:
            kwargs['hints'] = self.hints
        return (
            self.__class__.__name__,
            [],
            kwargs
        )

    @property
    def reversible(self):
        return self.reverse_code is not None

    def state_forwards(self, app_label, state):
        # RunPython objects have no state effect. To add some, combine this
        # with SeparateDatabaseAndState.
        pass

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        # RunPython has access to all models. Ensure that all models are
        # reloaded in case any are delayed.
        from_state.clear_delayed_apps_cache()
        self.code()

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        if self.reverse_code is None:
            raise NotImplementedError('You cannot reverse this operation')
        self.reverse_code()

    def describe(self):
        return 'Raw Python operation'

    @staticmethod
    def noop(apps, schema_editor):
        return None
