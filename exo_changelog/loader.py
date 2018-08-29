from __future__ import unicode_literals

import os
import sys
from importlib import import_module

from django.apps import apps

from django.utils import six

from .graph import ChangeGraph
from .recorder import ChangeRecorder
from .exceptions import (
    AmbiguityError, BadChangeError, InconsistentChangeHistory,
    NodeNotFoundError,
)

CHANGELOG_MODULE_NAME = 'changelog'


class ChangeLoader(object):
    """
    Loads changes files from disk, and their status from the database.

    Change files are expected to live in the "changelog" directory of
    an app. Their names are entirely unimportant from a code perspective,
    but will probably follow the 1234_name.py convention.

    On initialization, this class will scan those directories, and open and
    read the python files, looking for a class called Change, which should
    inherit from exo_changelog.change.Change. See
    exo_changelog.change for what that looks like.

    This does mean that this class MUST also talk to the database as well as
    to disk, but this is probably fine. We're already not just operating
    in memory.
    """

    def __init__(self, connection, load=True, ignore_no_changes=False):
        self.connection = connection
        self.disk_changes = None
        self.applied_changes = None
        self.ignore_no_changes = ignore_no_changes
        if load:
            self.build_graph()

    @classmethod
    def changes_module(cls, app_label):
        """
        Return the path to the changes module for the specified app_label
        and a boolean indicating if the module is specified in
        settings.CHANGE_MODULE.
        """
        app_package_name = apps.get_app_config(app_label).name
        return '%s.%s' % (app_package_name, CHANGELOG_MODULE_NAME), False

    def load_disk(self):
        """
        Loads the changes from all INSTALLED_APPS from disk.
        """
        self.disk_changes = {}
        self.unchanged_apps = set()
        self.changed_apps = set()
        for app_config in apps.get_app_configs():
            # Get the migrations module directory
            module_name, explicit = self.changes_module(app_config.label)
            if module_name is None:
                self.unchanged_apps.add(app_config.label)
                continue
            was_loaded = module_name in sys.modules
            try:
                module = import_module(module_name)
            except ImportError as e:
                # I hate doing this, but I don't want to squash other import errors.
                # Might be better to try a directory check directly.
                if ((explicit and self.ignore_no_changes) or (
                        not explicit and "No module named" in str(e) and CHANGELOG_MODULE_NAME in str(e))):
                    self.unchanged_apps.add(app_config.label)
                    continue
                raise
            else:
                # PY3 will happily import empty dirs as namespaces.
                if not hasattr(module, '__file__'):
                    self.unchanged_apps.add(app_config.label)
                    continue
                # Module is not a package (e.g. migrations.py).
                if not hasattr(module, '__path__'):
                    self.unchanged_apps.add(app_config.label)
                    continue
                # Force a reload if it's already loaded (tests need this)
                if was_loaded:
                    six.moves.reload_module(module)
            self.changed_apps.add(app_config.label)
            directory = os.path.dirname(module.__file__)
            # Scan for .py files
            change_names = set()
            for name in os.listdir(directory):
                if name.endswith(".py"):
                    import_name = name.rsplit(".", 1)[0]
                    if import_name[0] not in "_.~":
                        change_names.add(import_name)
            # Load them
            for change_name in change_names:
                change_module = import_module("%s.%s" % (module_name, change_name))
                if not hasattr(change_module, "Change"):
                    raise BadChangeError(
                        "Change %s in app %s has no Change class" % (change_name, app_config.label)
                    )
                self.disk_changes[app_config.label, change_name] = change_module.Change(
                    change_name,
                    app_config.label,
                )

    def get_change(self, app_label, name_prefix):
        "Gets the change exactly named, or raises `graph.NodeNotFoundError`"
        return self.graph.nodes[app_label, name_prefix]

    def get_change_by_prefix(self, app_label, name_prefix):
        "Returns the change(s) which match the given app label and name _prefix_"
        # Do the search
        results = []
        for change_app_label, change_name in self.disk_changes:
            if change_app_label == app_label and change_name.startswith(name_prefix):
                results.append((change_app_label, change_name))
        if len(results) > 1:
            raise AmbiguityError(
                "There is more than one change for '%s' with the prefix '%s'" % (app_label, name_prefix)
            )
        elif len(results) == 0:
            raise KeyError("There no change for '%s' with the prefix '%s'" % (app_label, name_prefix))
        else:
            return self.disk_changes[results[0]]

    def check_key(self, key, current_app):
        if (key[1] != "__first__" and key[1] != "__latest__") or key in self.graph:
            return key
        # Special-case __first__, which means "the first change" for
        # changed apps, and is ignored for unchanged apps. It allows
        # makechanges to declare dependencies on apps before they even have
        # changes.
        if key[0] == current_app:
            # Ignore __first__ references to the same app (#22325)
            return
        if key[0] in self.unchanged_apps:
            # This app isn't changes, but something depends on it.
            # The models will get auto-added into the state, though
            # so we're fine.
            return
        if key[0] in self.changed_apps:
            try:
                if key[1] == "__first__":
                    return list(self.graph.root_nodes(key[0]))[0]
                else:  # "__latest__"
                    return list(self.graph.leaf_nodes(key[0]))[0]
            except IndexError:
                if self.ignore_no_changes:
                    return None
                else:
                    raise ValueError("Dependency on app with no changes: %s" % key[0])
        raise ValueError("Dependency on unknown app: %s" % key[0])

    def add_internal_dependencies(self, key, change):
        """
        Internal dependencies need to be added first to ensure `__first__`
        dependencies find the correct root node.
        """
        for parent in change.dependencies:
            if parent[0] != key[0] or parent[1] == '__first__':
                # Ignore __first__ references to the same app (#22325).
                continue
            self.graph.add_dependency(change, key, parent, skip_validation=True)

    def add_external_dependencies(self, key, change):
        for parent in change.dependencies:
            # Skip internal dependencies
            if key[0] == parent[0]:
                continue
            parent = self.check_key(parent, key[0])
            if parent is not None:
                self.graph.add_dependency(change, key, parent, skip_validation=True)
        for child in change.run_before:
            child = self.check_key(child, key[0])
            if child is not None:
                self.graph.add_dependency(change, child, key, skip_validation=True)

    def build_graph(self):
        """
        Builds a change dependency graph using both the disk and database.
        You'll need to rebuild the graph if you apply change. This isn't
        usually a problem as generally change stuff runs in a one-shot process.
        """
        # Load disk data
        self.load_disk()
        # Load database data
        if self.connection is None:
            self.applied_changes = set()
        else:
            recorder = ChangeRecorder(self.connection)
            self.applied_changes = recorder.applied_changes()
        # To start, populate the migration graph with nodes for ALL migrations
        # and their dependencies. Also make note of replacing migrations at this step.
        self.graph = ChangeGraph()
        self.replacements = {}
        for key, change in self.disk_changes.items():
            self.graph.add_node(key, change)
            # Internal (aka same-app) dependencies.
            self.add_internal_dependencies(key, change)

        # Add external dependencies now that the internal ones have been resolved.
        for key, change in self.disk_changes.items():
            self.add_external_dependencies(key, change)

        # Ensure the graph is consistent.
        try:
            self.graph.validate_consistency()
        except NodeNotFoundError as exc:
            raise exc

    def check_consistent_history(self, connection):
        """
        Raise InconsistentChangeHistory if any applied changes have
        unapplied dependencies.
        """
        recorder = ChangeRecorder(connection)
        applied = recorder.applied_changes()
        for change in applied:
            # If the migration is unknown, skip it.
            if change not in self.graph.nodes:
                continue
            for parent in self.graph.node_map[change].parents:
                if parent not in applied:
                    raise InconsistentChangeHistory(
                        "Change {}.{} is applied before its dependency "
                        "{}.{} on database '{}'.".format(
                            change[0], change[1], parent[0], parent[1],
                            connection.alias,
                        )
                    )

    def detect_conflicts(self):
        """
        Looks through the loaded graph and detects any conflicts - apps
        with more than one leaf migration. Returns a dict of the app labels
        that conflict with the migration names that conflict.
        """
        seen_apps = {}
        conflicting_apps = set()
        for app_label, change_name in self.graph.leaf_nodes():
            if app_label in seen_apps:
                conflicting_apps.add(app_label)
            seen_apps.setdefault(app_label, set()).add(change_name)
        return {app_label: seen_apps[app_label] for app_label in conflicting_apps}

    def project_state(self, nodes=None, at_end=True):
        """
        Returns a ProjectState object representing the most recent state
        that the migrations we loaded represent.

        See graph.make_state for the meaning of "nodes" and "at_end"
        """
        return self.graph.make_state(nodes=nodes, at_end=at_end, real_apps=list(self.unchanged_apps))
