=============================
django-changelog
=============================

.. image:: https://badge.fury.io/py/django-changelog.svg
    :target: https://badge.fury.io/py/django-changelog

.. image:: https://travis-ci.org/ExOLever/django-changelog.svg
    :target: https://travis-ci.org/ExOLever/django-changelog

.. image:: https://codecov.io/gh/ExOLever/django-changelog/branch/master/graph/badge.svg
    :target: https://codecov.io/gh/ExOLever/django-changelog

Manage changelog as migrations

Documentation
-------------

The full documentation is at https://django-changelog.readthedocs.io.

We have two commands, similar to Django Migrations, code based on it. One command creates an empty file ready for write our python code for the change (as a template file with some basic dependencies). We can include commands call or query using our django models.

We manage dependencies between changes at the same way that Django does. And also, we can manage conflicts through merging.

We only have two operations developed: RunPython and RunSQL (both of them, without parameters)
When you want to apply for changes, please execute applychange with/without app_label. You will see messages similar to migrations.


Quickstart
----------

Install django-changelog::

`pip install git+https://github.com/ExOLever/django-changelog.git@0.1.0`

Add it to your `INSTALLED_APPS`:

.. code-block:: python

    INSTALLED_APPS = (
        ...
        'exo_changelog.apps.ExoChangelogConfig',
        ...
    )
  
Add django-changelog's URL patterns:

.. code-block:: python

    from exo_changelog import urls as exo_changelog_urls


Create the changelog table:
`./manage.py migrate exo_changelog`


Features
--------

* Create an empty change:  ./manage.py makechange <app_name>
* Execute changes: ./manage.py applychange <app_name>


Credits
-------

Tools used in rendering this package:

*  Cookiecutter_
*  `cookiecutter-djangopackage`_

.. _Cookiecutter: https://github.com/audreyr/cookiecutter
.. _`cookiecutter-djangopackage`: https://github.com/pydanny/cookiecutter-djangopackage
