import io
import os
import sys
from itertools import takewhile

from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import DEFAULT_DB_ALIAS, connections, router
from django.db.migrations.questioner import (
    InteractiveMigrationQuestioner, MigrationQuestioner,
    NonInteractiveMigrationQuestioner,
)
from django.db.migrations.state import ProjectState
from django.db.migrations.utils import get_migration_name_timestamp
from django.utils.six import iteritems
from django.utils.six.moves import zip

from ...change import Change
from ...loader import ChangeLoader
from ...writer import ChangeWriter
from ...autodetector import ChangeAutodetector


class Command(BaseCommand):
    help = "Creates new change(s) for apps."

    def add_arguments(self, parser):
        parser.add_argument(
            'args', metavar='app_label', nargs='*',
            help='Specify the app label(s) to create change for.',
        )
        parser.add_argument(
            '--merge', action='store_true', dest='merge', default=False,
            help="Enable fixing of changes conflicts.",
        )
        parser.add_argument(
            '--noinput', '--no-input',
            action='store_false', dest='interactive', default=True,
            help='Tells Django to NOT prompt the user for input of any kind.',
        )
        parser.add_argument(
            '-n', '--name', action='store', dest='name', default=None,
            help="Use this name for change file(s).",
        )

    def handle(self, *app_labels, **options):
        self.verbosity = options['verbosity']
        self.interactive = options['interactive']
        self.merge = options['merge']
        self.change_name = options['name']
        self.dry_run = False
        # Make sure the app they asked for exists
        app_labels = set(app_labels)
        bad_app_labels = set()
        for app_label in app_labels:
            try:
                apps.get_app_config(app_label)
            except LookupError:
                bad_app_labels.add(app_label)
        if bad_app_labels:
            for app_label in bad_app_labels:
                self.stderr.write("App '%s' could not be found. Is it in INSTALLED_APPS?" % app_label)
            sys.exit(2)

        # Load the current graph state. Pass in None for the connection so
        # the loader doesn't try to resolve replaced changes from DB.
        loader = ChangeLoader(None, ignore_no_changes=True)

        # Raise an error if any changes are applied before their dependencies.
        consistency_check_labels = set(config.label for config in apps.get_app_configs())
        # Non-default databases are only checked if database routers used.
        aliases_to_check = connections if settings.DATABASE_ROUTERS else [DEFAULT_DB_ALIAS]
        for alias in sorted(aliases_to_check):
            connection = connections[alias]
            if (connection.settings_dict['ENGINE'] != 'django.db.backends.dummy' and any(
                    # At least one model must be migrated to the database.
                    router.allow_migrate(connection.alias, app_label, model_name=model._meta.object_name)
                    for app_label in consistency_check_labels
                    for model in apps.get_app_config(app_label).get_models()
            )):
                loader.check_consistent_history(connection)

        # Before anything else, see if there's conflicting apps and drop out
        # hard if there are any and they don't want to merge
        conflicts = loader.detect_conflicts()

        # If app_labels is specified, filter out conflicting changes for unspecified apps
        if app_labels:
            conflicts = {
                app_label: conflict for app_label, conflict in iteritems(conflicts)
                if app_label in app_labels
            }

        if conflicts and not self.merge:
            name_str = "; ".join(
                "%s in %s" % (", ".join(names), app)
                for app, names in conflicts.items()
            )
            raise CommandError(
                "Conflicting changes detected; multiple leaf nodes in the "
                "changes graph: (%s).\nTo fix them run "
                "'python manage.py makechange --merge'" % name_str
            )

        # If they want to merge and there's nothing to merge, then politely exit
        if self.merge and not conflicts:
            self.stdout.write("No conflicts detected to merge.")
            return

        # If they want to merge and there is something to merge, then
        # divert into the merge code
        if self.merge and conflicts:
            return self.handle_merge(loader, conflicts)

        if self.interactive:
            questioner = InteractiveMigrationQuestioner(specified_apps=app_labels, dry_run=self.dry_run)
        else:
            questioner = NonInteractiveMigrationQuestioner(specified_apps=app_labels, dry_run=self.dry_run)

        # To make an empty change, make one for each app
        if not app_labels:
            raise CommandError("You must supply at least one app label when using --empty.")
        # Make a fake changes() result we can pass to arrange_for_graph
        changes = {
            app: [Change("custom", app)]
            for app in app_labels
        }
        autodetector = ChangeAutodetector(
            loader.project_state(),
            ProjectState.from_apps(apps),
            questioner,
        )
        changes = autodetector.arrange_for_graph(
            changes=changes,
            graph=loader.graph,
            change_name=self.change_name,
        )
        self.write_changes_files(changes)

    def write_changes_files(self, changes):
        """
        Takes a changes dict and writes them out as changes files.
        """
        directory_created = {}
        for app_label, app_changes in changes.items():
            if self.verbosity >= 1:
                self.stdout.write(self.style.MIGRATE_HEADING("Changes for '%s':" % app_label) + "\n")
            for change in app_changes:
                # Describe the change
                writer = ChangeWriter(change)
                if self.verbosity >= 1:
                    # Display a relative path if it's below the current working
                    # directory, or an absolute path otherwise.
                    try:
                        change_string = os.path.relpath(writer.path)
                    except ValueError:
                        change_string = writer.path
                    if change_string.startswith('..'):
                        change_string = writer.path
                    self.stdout.write("  %s\n" % (self.style.MIGRATE_LABEL(change_string),))
                    for operation in change.operations:
                        self.stdout.write("    - %s\n" % operation.describe())
                if not self.dry_run:
                    # Write the changes file to the disk.
                    changes_directory = os.path.dirname(writer.path)
                    if not directory_created.get(app_label):
                        if not os.path.isdir(changes_directory):
                            os.mkdir(changes_directory)
                        init_path = os.path.join(changes_directory, "__init__.py")
                        if not os.path.isfile(init_path):
                            open(init_path, "w").close()
                        # We just do this once per app
                        directory_created[app_label] = True
                    change_string = writer.as_string()
                    with io.open(writer.path, "w", encoding='utf-8') as fh:
                        fh.write(change_string)
                elif self.verbosity == 3:
                    # Alternatively, makechanges --dry-run --verbosity 3
                    # will output the changes to stdout rather than saving
                    # the file to the disk.
                    self.stdout.write(self.style.MIGRATE_HEADING(
                        "Full changes file '%s':" % writer.filename) + "\n"
                    )
                    self.stdout.write("%s\n" % writer.as_string())

    def handle_merge(self, loader, conflicts):
        """
        Handles merging together conflicted changes interactively,
        if it's safe; otherwise, advises on how to fix it.
        """
        if self.interactive:
            questioner = InteractiveMigrationQuestioner()
        else:
            questioner = MigrationQuestioner(defaults={'ask_merge': True})

        for app_label, change_names in conflicts.items():
            # Grab out the changes in question, and work out their
            # common ancestor.
            merge_changes = []
            for change_name in change_names:
                change = loader.get_change(app_label, change_name)
                change.ancestry = [
                    mig for mig in loader.graph.forwards_plan((app_label, change_name))
                    if mig[0] == change.app_label
                ]
                merge_changes.append(change)

            def all_items_equal(seq):
                return all(item == seq[0] for item in seq[1:])

            merge_changes_generations = zip(*[m.ancestry for m in merge_changes])
            common_ancestor_count = sum(1 for common_ancestor_generation
                                        in takewhile(all_items_equal, merge_changes_generations))
            if not common_ancestor_count:
                raise ValueError("Could not find common ancestor of %s" % change_names)
            # Now work out the operations along each divergent branch
            for change in merge_changes:
                change.branch = change.ancestry[common_ancestor_count:]
                changes_ops = (loader.get_change(node_app, node_name).operations
                                  for node_app, node_name in change.branch)
                change.merged_operations = sum(changes_ops, [])
            # In future, this could use some of the Optimizer code
            # (can_optimize_through) to automatically see if they're
            # mergeable. For now, we always just prompt the user.
            if self.verbosity > 0:
                self.stdout.write(self.style.MIGRATE_HEADING("Merging %s" % app_label))
                for change in merge_changes:
                    self.stdout.write(self.style.MIGRATE_LABEL("  Branch %s" % change.name))
                    for operation in change.merged_operations:
                        self.stdout.write("    - %s\n" % operation.describe())
            if questioner.ask_merge(app_label):
                # If they still want to merge it, then write out an empty
                # file depending on the changes needing merging.
                numbers = [
                    ChangeAutodetector.parse_number(change.name)
                    for change in merge_changes
                ]
                try:
                    biggest_number = max(x for x in numbers if x is not None)
                except ValueError:
                    biggest_number = 1
                subclass = type("Change", (Change, ), {
                    "dependencies": [(app_label, change.name) for change in merge_changes],
                })
                change_name = "%04i_%s" % (
                    biggest_number + 1,
                    self.change_name or ("merge_%s" % get_migration_name_timestamp())
                )
                new_change = subclass(change_name, app_label)
                writer = ChangeWriter(new_change)

                if not self.dry_run:
                    # Write the merge changes file to the disk
                    with io.open(writer.path, "w", encoding='utf-8') as fh:
                        fh.write(writer.as_string())
                    if self.verbosity > 0:
                        self.stdout.write("\nCreated new merge change %s" % writer.path)
                elif self.verbosity == 3:
                    # Alternatively, makechanges --merge --dry-run --verbosity 3
                    # will output the merge changes to stdout rather than saving
                    # the file to the disk.
                    self.stdout.write(self.style.MIGRATE_HEADING(
                        "Full merge changes file '%s':" % writer.filename) + "\n"
                    )
                    self.stdout.write("%s\n" % writer.as_string())
