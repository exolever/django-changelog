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

Quickstart
----------

Install django-changelog::

    pip install git+https://github.com/ExOLever/django-changelog.git@0.1.0

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


    urlpatterns = [
        ...
        url(r'^', include(exo_changelog_urls)),
        ...
    ]

Features
--------

* TODO

Running Tests
-------------

Does the code actually work?

::

    source <YOURVIRTUALENV>/bin/activate
    (myenv) $ pip install tox
    (myenv) $ tox

Credits
-------

Tools used in rendering this package:

*  Cookiecutter_
*  `cookiecutter-djangopackage`_

.. _Cookiecutter: https://github.com/audreyr/cookiecutter
.. _`cookiecutter-djangopackage`: https://github.com/pydanny/cookiecutter-djangopackage
