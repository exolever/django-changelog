from __future__ import unicode_literals

from django.db.migrations.state import ProjectState
from django.db import DEFAULT_DB_ALIAS, connections

from .exceptions import InvalidChangePlan
from .loader import ChangeLoader
from .recorder import ChangeRecorder


class ChangeExecutor(object):
    """
    End-to-end change execution - loads changes, and runs them
    up or down to a specified set of targets.
    """

    def __init__(self, progress_callback=None):
        self.connection = connections[DEFAULT_DB_ALIAS]
        self.loader = ChangeLoader(self.connection)
        self.recorder = ChangeRecorder(self.connection)
        self.progress_callback = progress_callback

    def change_plan(self, targets, clean_start=False):
        """
        Given a set of targets, returns a list of (Change instance, backwards?).
        """
        plan = []
        if clean_start:
            applied = set()
        else:
            applied = set(self.loader.applied_changes)
        for target in targets:
            # If the target is (app_label, None), that means unchange everything
            if target[1] is None:
                for root in self.loader.graph.root_nodes():
                    if root[0] == target[0]:
                        for change in self.loader.graph.backwards_plan(root):
                            if change in applied:
                                plan.append((self.loader.graph.nodes[change], True))
                                applied.remove(change)
            # If the change is already applied, do backwards mode,
            # otherwise do forwards mode.
            elif target in applied:
                # Don't change backwards all the way to the target node (that
                # may roll back dependencies in other apps that don't need to
                # be rolled back); instead roll back through target's immediate
                # child(ren) in the same app, and no further.
                next_in_app = sorted(
                    n for n in
                    self.loader.graph.node_map[target].children
                    if n[0] == target[0]
                )
                for node in next_in_app:
                    for change in self.loader.graph.backwards_plan(node):
                        if change in applied:
                            plan.append((self.loader.graph.nodes[change], True))
                            applied.remove(change)
            else:
                for change in self.loader.graph.forwards_plan(target):
                    if change not in applied:
                        plan.append((self.loader.graph.nodes[change], False))
                        applied.add(change)
        return plan

    def _create_project_state(self, with_applied_changes=False):
        """
        Create a project state including all the applications without
        changes and applied changes if with_applied_changes=True.
        """
        state = ProjectState(real_apps=list(self.loader.unchanged_apps))
        if with_applied_changes:
            # Create the forwards plan Django would follow on an empty database
            full_plan = self.change_plan(self.loader.graph.leaf_nodes(), clean_start=True)
            applied_changes = {
                self.loader.graph.nodes[key] for key in self.loader.applied_changes
                if key in self.loader.graph.nodes
            }
            for change, _ in full_plan:
                if change in applied_changes:
                    change.mutate_state(state, preserve=False)
        return state

    def change(self, targets, plan=None, state=None, fake=False):
        """
        Changes up to the given targets.

        Django first needs to create all project states before a change is
        (un)applied and in a second step run all the database operations.
        """
        if plan is None:
            plan = self.change_plan(targets)
        # Create the forwards plan Django would follow on an empty database
        full_plan = self.change_plan(self.loader.graph.leaf_nodes(), clean_start=True)

        all_forwards = all(not backwards for mig, backwards in plan)
        all_backwards = all(backwards for mig, backwards in plan)

        if not plan:
            if state is None:
                # The resulting state should include applied changes.
                state = self._create_project_state(with_applied_changes=True)
        elif all_forwards == all_backwards:
            # This should only happen if there's a mixed plan
            raise InvalidChangePlan(
                'Change plans with both forwards and backwards changes '
                'are not supported. Please split your change process into '
                'separate plans of only forwards OR backwards changes.',
                plan
            )
        elif all_forwards:
            if state is None:
                # The resulting state should still include applied changes.
                state = self._create_project_state(with_applied_changes=True)
            state = self._change_all_forwards(state, plan, full_plan, fake=fake)
        else:
            # No need to check for `elif all_backwards` here, as that condition
            # would always evaluate to true.
            state = self._migrate_all_backwards(plan, full_plan, fake=fake)

        return state

    def _change_all_forwards(self, state, plan, full_plan, fake):
        """
        Take a list of 2-tuples of the form (change instance, False) and
        apply them in the order they occur in the full_plan.
        """
        changes_to_run = {m[0] for m in plan}
        for change, _ in full_plan:
            if not changes_to_run:
                # We remove every change that we applied from these sets so
                # that we can bail out once the last change has been applied
                # and don't always run until the very end of the change
                # process.
                break
            if change in changes_to_run:
                if 'apps' not in state.__dict__:
                    if self.progress_callback:
                        self.progress_callback('render_start')
                    state.apps  # Render all -- performance critical
                    if self.progress_callback:
                        self.progress_callback('render_success')
                state = self.apply_change(state, change, fake=fake)
                changes_to_run.remove(change)

        return state

    def _change_all_backwards(self, plan, full_plan, fake):
        """
        Take a list of 2-tuples of the form (change instance, True) and
        unapply them in reverse order they occur in the full_plan.

        Since unapplying a change requires the project state prior to that
        change, Django will compute the change states before each of them
        in a first run over the plan and then unapply them in a second run over
        the plan.
        """
        changes_to_run = {m[0] for m in plan}
        # Holds all change states prior to the changes being unapplied
        states = {}
        state = self._create_project_state()
        applied_changes = {
            self.loader.graph.nodes[key] for key in self.loader.applied_changes
            if key in self.loader.graph.nodes
        }
        if self.progress_callback:
            self.progress_callback('render_start')
        for change, _ in full_plan:
            if not changes_to_run:
                # We remove every change that we applied from this set so
                # that we can bail out once the last change has been applied
                # and don't always run until the very end of the change
                # process.
                break
            if change in changes_to_run:
                if 'apps' not in state.__dict__:
                    state.apps  # Render all -- performance critical
                # The state before this change
                states[change] = state
                # The old state keeps as-is, we continue with the new state
                state = change.mutate_state(state, preserve=True)
                changes_to_run.remove(change)
            elif change in applied_changes:
                # Only mutate the state if the change is actually applied
                # to make sure the resulting state doesn't include changes
                # from unrelated migrations.
                change.mutate_state(state, preserve=False)
        if self.progress_callback:
            self.progress_callback('render_success')

        for change, _ in plan:
            self.unapply_change(states[change], change, fake=fake)
            applied_changes.remove(change)

        # Generate the post change state by starting from the state before
        # the last change is unapplied and mutating it to include all the
        # remaining applied migrations.
        last_unapplied_change = plan[-1][0]
        state = states[last_unapplied_change]
        for index, (change, _) in enumerate(full_plan):
            if change == last_unapplied_change:
                for change, _ in full_plan[index:]:
                    if change in applied_changes:
                        change.mutate_state(state, preserve=False)
                break

        return state

    def apply_change(self, state, change, fake=False):
        """
        Runs a migration forwards.
        """
        if self.progress_callback:
            self.progress_callback('apply_start', change, fake)
        if not fake:
            state = change.apply(state, None)
        # Record individual statuses
        self.recorder.record_applied(change.app_label, change.name)
        # Report progress
        if self.progress_callback:
            self.progress_callback('apply_success', change, fake)
        return state

    def unapply_change(self, state, change, fake=False):
        """
        Runs a migration backwards.
        """
        if self.progress_callback:
            self.progress_callback('unapply_start', change, fake)
        if not fake:
            with self.connection.schema_editor(atomic=change.atomic) as schema_editor:
                state = change.unapply(state, schema_editor)
        # For replacement changes, record individual statuses
        self.recorder.record_unapplied(change.app_label, change.name)
        # Report progress
        if self.progress_callback:
            self.progress_callback('unapply_success', change, fake)
        return state
