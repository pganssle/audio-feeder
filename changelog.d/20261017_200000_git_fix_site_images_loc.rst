Bugfixes
--------

- The default cover image is now copied into the directory configured by ``site_images_loc``, which is where the site expects it, rather than into ``site-images`` in the static directory. It's copied by ``audio-feeder install`` and whenever the server starts, so existing installations get it without being reinstalled. (`#107 <https://github.com/pganssle/audio-feeder/issues/107>`_)
