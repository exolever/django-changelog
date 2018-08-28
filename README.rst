=============================
exo-changelog
=============================

.. image:: https://badge.fury.io/py/exo-changelog.svg
    :target: https://badge.fury.io/py/exo-changelog

.. image:: https://travis-ci.org/tomasgarzon/exo-changelog.svg?branch=master
    :target: https://travis-ci.org/tomasgarzon/exo-changelog

.. image:: https://codecov.io/gh/tomasgarzon/exo-changelog/branch/master/graph/badge.svg
    :target: https://codecov.io/gh/tomasgarzon/exo-changelog

Manage changelog as migrations

Documentation
-------------

The full documentation is at https://exo-changelog.readthedocs.io.

Quickstart
----------

Install exo-changelog::

    pip install exo-changelog

Add it to your `INSTALLED_APPS`:

.. code-block:: python

    INSTALLED_APPS = (
        ...
        'exo_changelog.apps.ExoChangelogConfig',
        ...
    )

Add exo-changelog's URL patterns:

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
