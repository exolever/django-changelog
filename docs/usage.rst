=====
Usage
=====

To use exo-changelog in a project, add it to your `INSTALLED_APPS`:

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
