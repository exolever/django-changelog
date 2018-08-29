# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import time
from importlib import import_module

from django.apps import apps
from django.core.checks import Tags, run_checks
from django.core.management.base import BaseCommand, CommandError

from django.utils.module_loading import module_has_submodule

from ...exceptions import AmbiguityError
from ...executor import ChangeExecutor


class Command(BaseCommand):
    help = 'Apply changes. '

    def add_arguments(self, parser):
        parser.add_argument(
            'app_label', nargs='?',
            help='App label of an application to synchronize the state.',
        )
        parser.add_argument(
            'change_name', nargs='?',
            help='Database state will be brought to the state after that '
                 'change. Use the name "zero" to unapply all changes.',
        )
        parser.add_argument(
            '--noinput', '--no-input',
            action='store_false', dest='interactive', default=True,
            help='Tells Django to NOT prompt the user for input of any kind.',
        )
        parser.add_argument(
            '--fake', action='store_true', dest='fake', default=False,
            help='Mark changes as run without actually running them.',
        )

    def _run_checks(self, **kwargs):
        issues = run_checks(tags=[Tags.database])
        issues.extend(super(Command, self)._run_checks(**kwargs))
        return issues

    def handle(self, *args, **options):

        self.verbosity = options['verbosity']
        self.interactive = options['interactive']

        # Import the 'management' module within each installed app, to register
        # dispatcher events.
        for app_config in apps.get_app_configs():
            if module_has_submodule(app_config.module, 'management'):
                import_module('.management', app_config.name)

        executor = ChangeExecutor(self.change_progress_callback)

        # Raise an error if any migrations are applied before their dependencies.
        executor.loader.check_consistent_history(None)

        # Before anything else, see if there's conflicting apps and drop out
        # hard if there are any
        conflicts = executor.loader.detect_conflicts()
        if conflicts:
            name_str = '; '.join(
                '%s in %s' % (', '.join(names), app)
                for app, names in conflicts.items()
            )
            raise CommandError(
                'Conflicting changes detected; multiple leaf nodes in the '
                'change graph: (%s).\nTo fix them run '
                "'python manage.py makechange --merge'" % name_str
            )

        # If they supplied command line arguments, work out what they mean.
        target_app_labels_only = True
        if options['app_label'] and options['change_name']:
            app_label, change_name = options['app_label'], options['migration_name']
            if app_label not in executor.loader.changed_apps:
                raise CommandError(
                    "App '%s' does not have changes." % app_label
                )
            if change_name == 'zero':
                targets = [(app_label, None)]
            else:
                try:
                    change = executor.loader.get_change_by_prefix(app_label, change_name)
                except AmbiguityError:
                    raise CommandError(
                        "More than one change matches '%s' in app '%s'. "
                        'Please be more specific.' %
                        (change_name, app_label)
                    )
                except KeyError:
                    raise CommandError("Cannot find a change matching '%s' from app '%s'." % (
                        change_name, app_label))
                targets = [(app_label, change.name)]
            target_app_labels_only = False
        elif options['app_label']:
            app_label = options['app_label']
            if app_label not in executor.loader.changed_apps:
                raise CommandError(
                    "App '%s' does not have changes." % app_label
                )
            targets = [key for key in executor.loader.graph.leaf_nodes() if key[0] == app_label]
        else:
            targets = executor.loader.graph.leaf_nodes()

        plan = executor.change_plan(targets)

        # Print some useful info
        if self.verbosity >= 1:
            self.stdout.write(self.style.MIGRATE_HEADING('Operations to perform:'))
            if target_app_labels_only:
                self.stdout.write(
                    self.style.MIGRATE_LABEL('  Apply all changes: ') +
                    (', '.join(sorted({a for a, n in targets})) or '(none)')
                )
            else:
                if targets[0][1] is None:
                    self.stdout.write(self.style.MIGRATE_LABEL(
                        '  Unapply all changes: ') + '%s' % (targets[0][0], )
                    )
                else:
                    self.stdout.write(self.style.MIGRATE_LABEL(
                        '  Target specific change: ') + '%s, from %s'
                        % (targets[0][1], targets[0][0])
                    )

        pre_change_state = executor._create_project_state(with_applied_changes=True)

        # Change!
        if self.verbosity >= 1:
            self.stdout.write(self.style.MIGRATE_HEADING('Running changes:'))
        if not plan:
            if self.verbosity >= 1:
                self.stdout.write('  No changes to apply.')
            fake = False
        else:
            fake = options['fake']
        post_change_state = executor.change(
            targets, plan=plan, state=pre_change_state.clone(), fake=fake,
        )
        # are reloaded in case any are delayed.
        post_change_state.clear_delayed_apps_cache()

    def change_progress_callback(self, action, change=None, fake=False):
        if self.verbosity >= 1:
            compute_time = self.verbosity > 1
            if action == 'apply_start':
                if compute_time:
                    self.start = time.time()
                self.stdout.write('  Applying %s...' % change, ending='')
                self.stdout.flush()
            elif action == 'apply_success':
                elapsed = ' (%.3fs)' % (time.time() - self.start) if compute_time else ''
                if fake:
                    self.stdout.write(self.style.SUCCESS(' FAKED' + elapsed))
                else:
                    self.stdout.write(self.style.SUCCESS(' OK' + elapsed))
            elif action == 'unapply_start':
                if compute_time:
                    self.start = time.time()
                self.stdout.write('  Unapplying %s...' % change, ending='')
                self.stdout.flush()
            elif action == 'unapply_success':
                elapsed = ' (%.3fs)' % (time.time() - self.start) if compute_time else ''
                if fake:
                    self.stdout.write(self.style.SUCCESS(' FAKED' + elapsed))
                else:
                    self.stdout.write(self.style.SUCCESS(' OK' + elapsed))
            elif action == 'render_start':
                if compute_time:
                    self.start = time.time()
                self.stdout.write('  Rendering model states...', ending='')
                self.stdout.flush()
            elif action == 'render_success':
                elapsed = ' (%.3fs)' % (time.time() - self.start) if compute_time else ''
                self.stdout.write(self.style.SUCCESS(' DONE' + elapsed))
