from __future__ import unicode_literals

from six import python_2_unicode_compatible


@python_2_unicode_compatible
class Change(object):
    """
    The base class for all changes.

    Migration files will import this from exo_changelog.change.Change
    and subclass it as a class called Change. It will have one or more
    of the following attributes:

     - operations: A list of Operation instances
     - dependencies: A list of tuples of (app_path, migration_name)

    """

    # Operations to apply during this change, in order.
    operations = []

    # Other migrations that should be run before this change.
    dependencies = []

    # Other changes that should be run after this one (i.e. have
    # this change added to their dependencies). Useful to make third-party
    # apps' changes run after your AUTH_USER replacement, for example.
    run_before = []

    initial = None

    def __init__(self, name, app_label, description=None):
        self.name = name
        self.app_label = app_label
        self.description = description or ''
        # Copy dependencies & other attrs as we might mutate them at runtime
        self.operations = list(self.__class__.operations)
        self.dependencies = list(self.__class__.dependencies)

    def __eq__(self, other):
        if not isinstance(other, Change):
            return False
        return (self.name == other.name) and (self.app_label == other.app_label)

    def __ne__(self, other):
        return not (self == other)

    def __repr__(self):
        return '<Change %s.%s>' % (self.app_label, self.name)

    def __str__(self):
        return '%s.%s' % (self.app_label, self.name)

    def __hash__(self):
        return hash('%s.%s' % (self.app_label, self.name))

    def mutate_state(self, project_state, preserve=True):
        """
        Takes a ProjectState and returns a new one with the change's
        operations applied to it. Preserves the original object state by
        default and will return a mutated state from a copy.
        """
        new_state = project_state
        if preserve:
            new_state = project_state.clone()

        for operation in self.operations:
            operation.state_forwards(self.app_label, new_state)
        return new_state

    def apply(self, project_state, collect_sql=False):
        """
        Takes a project_state representing all changes prior to this one
        and applies the change
        in a forwards order.

        Returns the resulting project state for efficient re-use by following
        Changes.
        """
        for operation in self.operations:
            # Save the state before the operation has run
            old_state = project_state.clone()
            operation.database_forwards(
                self.app_label, None, old_state, project_state)
        return project_state


class SwappableTuple(tuple):
    """
    Subclass of tuple so Django can tell this was originally a swappable
    dependency when it reads the migration file.
    """

    def __new__(cls, value, setting):
        self = tuple.__new__(cls, value)
        self.setting = setting
        return self


def swappable_dependency(value):
    """
    Turns a setting value into a dependency.
    """
    return SwappableTuple((value.split('.', 1)[0], '__first__'), value)
