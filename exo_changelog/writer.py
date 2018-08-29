from __future__ import unicode_literals

import os
import re
from importlib import import_module

from django import get_version
from django.apps import apps
from django.db.migrations.writer import OperationWriter
from django.db.migrations.serializer import serializer_factory
from django.utils._os import upath
from django.utils.encoding import force_text
from django.utils.module_loading import module_dir
from django.utils.timezone import now

from .loader import ChangeLoader

try:
    import enum
except ImportError:
    # No support on Python 2 if enum34 isn't installed.
    enum = None


class ChangeWriter(object):
    """
    Takes a Change instance and is able to produce the contents
    of the migration file from it.
    """

    def __init__(self, change):
        self.change = change
        self.needs_manual_porting = False

    def as_string(self):
        """
        Returns a string of the file contents.
        """
        items = {
            "replaces_str": "",
            "initial_str": "",
        }

        imports = set()

        # Deconstruct operations
        operations = []
        for operation in self.change.operations:
            operation_string, operation_imports = OperationWriter(operation).serialize()
            imports.update(operation_imports)
            operations.append(operation_string)
        items["operations"] = "\n".join(operations) + "\n" if operations else ""

        # Format dependencies and write out swappable dependencies right
        dependencies = []
        for dependency in self.change.dependencies:
            if dependency[0] == "__setting__":
                dependencies.append("        migrations.swappable_dependency(settings.%s)," % dependency[1])
                imports.add("from django.conf import settings")
            else:
                # No need to output bytestrings for dependencies
                dependency = tuple(force_text(s) for s in dependency)
                dependencies.append("        %s," % self.serialize(dependency)[0])
        items["dependencies"] = "\n".join(dependencies) + "\n" if dependencies else ""

        # Format imports nicely, swapping imports of functions from migration files
        # for comments
        migration_imports = set()
        for line in list(imports):
            if re.match(r"^import (.*)\.\d+[^\s]*$", line):
                migration_imports.add(line.split("import")[1].strip())
                imports.remove(line)
                self.needs_manual_porting = True

        # django.db.migrations is always used, but models import may not be.
        imports.add("from exo_changelog import change, operations")

        # Sort imports by the package / module to be imported (the part after
        # "from" in "from ... import ..." or after "import" in "import ...").
        sorted_imports = sorted(imports, key=lambda i: i.split()[1])
        items["imports"] = "\n".join(sorted_imports) + "\n" if imports else ""
        if migration_imports:
            items["imports"] += (
                "\n\n# Functions from the following migrations need manual "
                "copying.\n# Move them and any dependencies into this file, "
                "then update the\n# RunPython operations to refer to the local "
                "versions:\n# %s"
            ) % "\n# ".join(sorted(migration_imports))

        # Hinting that goes into comment
        items.update(
            version=get_version(),
            timestamp=now().strftime("%Y-%m-%d %H:%M"),
        )

        if self.change.initial:
            items['initial_str'] = "\n    initial = True\n"

        return CHANGE_TEMPLATE % items

    @property
    def basedir(self):
        changes_package_name, _ = ChangeLoader.changes_module(self.change.app_label)

        if changes_package_name is None:
            raise ValueError(
                "Django can't create changes for app '%s' because "
                "changes have been disabled via the CHANGES_MODULES "
                "setting." % self.change.app_label
            )

        # See if we can import the migrations module directly
        try:
            changes_module = import_module(changes_package_name)
        except ImportError:
            pass
        else:
            try:
                return upath(module_dir(changes_module))
            except ValueError:
                pass

        # Alright, see if it's a direct submodule of the app
        app_config = apps.get_app_config(self.change.app_label)
        maybe_app_name, _, changes_package_basename = changes_package_name.rpartition(".")
        if app_config.name == maybe_app_name:
            return os.path.join(app_config.path, changes_package_basename)

        # In case of using CHANGE_MODULES setting and the custom package
        # doesn't exist, create one, starting from an existing package
        existing_dirs, missing_dirs = changes_package_name.split("."), []
        while existing_dirs:
            missing_dirs.insert(0, existing_dirs.pop(-1))
            try:
                base_module = import_module(".".join(existing_dirs))
            except ImportError:
                continue
            else:
                try:
                    base_dir = upath(module_dir(base_module))
                except ValueError:
                    continue
                else:
                    break
        else:
            raise ValueError(
                "Could not locate an appropriate location to create "
                "changes package %s. Make sure the toplevel "
                "package exists and can be imported." %
                changes_package_name)

        final_dir = os.path.join(base_dir, *missing_dirs)
        if not os.path.isdir(final_dir):
            os.makedirs(final_dir)
        for missing_dir in missing_dirs:
            base_dir = os.path.join(base_dir, missing_dir)
            with open(os.path.join(base_dir, "__init__.py"), "w"):
                pass

        return final_dir

    @property
    def filename(self):
        return "%s.py" % self.change.name

    @property
    def path(self):
        return os.path.join(self.basedir, self.filename)

    @classmethod
    def serialize(cls, value):
        return serializer_factory(value).serialize()


CHANGE_TEMPLATE = """\
# -*- coding: utf-8 -*-
# Generated for Django %(version)s on %(timestamp)s
from __future__ import unicode_literals

%(imports)s

class Change(change.Change):
%(replaces_str)s%(initial_str)s
    dependencies = [
%(dependencies)s\
    ]

    operations = [
%(operations)s\
    ]
"""
