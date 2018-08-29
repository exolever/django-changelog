from __future__ import unicode_literals
import re

from django.db.migrations.questioner import MigrationQuestioner
from django.db.migrations.utils import get_migration_name_timestamp


class ChangeAutodetector(object):
    """
    Takes a pair of ProjectStates, and compares them to see what the
    first would need doing to make it match the second (the second
    usually being the project's current state).

    Note that this naturally operates on entire projects at a time,
    as it's likely that changes interact (for example, you can't
    add a ForeignKey without having a migration to add the table it
    depends on first). A user interface may offer single-app usage
    if it wishes, with the caveat that it may not always be possible.
    """

    def __init__(self, from_state, to_state, questioner=None):
        self.from_state = from_state
        self.to_state = to_state
        self.questioner = questioner or MigrationQuestioner()
        self.existing_apps = {app for app, model in from_state.models}

    def arrange_for_graph(self, changes, graph, change_name=None):
        """
        Takes in a result from changes() and a ChangeGraph,
        and fixes the names and dependencies of the changes so they
        extend the graph from the leaf nodes for each app.
        """
        leaves = graph.leaf_nodes()
        name_map = {}
        for app_label, changelogs in list(changes.items()):
            if not changelogs:
                continue
            # Find the app label's current leaf node
            app_leaf = None
            for leaf in leaves:
                if leaf[0] == app_label:
                    app_leaf = leaf
                    break
            # Do they want an initial migration for this app?
            if app_leaf is None and not self.questioner.ask_initial(app_label):
                # They don't.
                for change in changelogs:
                    name_map[(app_label, change.name)] = (app_label, '__first__')
                del changes[app_label]
                continue
            # Work out the next number in the sequence
            if app_leaf is None:
                next_number = 1
            else:
                next_number = (self.parse_number(app_leaf[1]) or 0) + 1
            # Name each migration
            for i, change in enumerate(changelogs):
                if i == 0 and app_leaf:
                    change.dependencies.append(app_leaf)
                if i == 0 and not app_leaf:
                    new_name = '0001_%s' % change_name if change_name else '0001_initial'
                else:
                    new_name = '%04i_%s' % (
                        next_number,
                        change_name or self.suggest_name(change.operations)[:100],
                    )
                name_map[(app_label, change.name)] = (app_label, new_name)
                next_number += 1
                change.name = new_name
        # Now fix dependencies
        for app_label, changelogs in changes.items():
            for change in changelogs:
                change.dependencies = [name_map.get(d, d) for d in change.dependencies]
        return changes

    @classmethod
    def suggest_name(cls, ops):
        """
        Given a set of operations, suggests a name for the change
        they might represent. Names are not guaranteed to be unique,
        but we put some effort in to the fallback name to avoid VCS conflicts
        if we can.
        """
        return 'auto_%s' % get_migration_name_timestamp()

    @classmethod
    def parse_number(cls, name):
        """
        Given a migration name, tries to extract a number from the
        beginning of it. If no number found, returns None.
        """
        match = re.match(r'^\d+', name)
        if match:
            return int(match.group())
        return None
