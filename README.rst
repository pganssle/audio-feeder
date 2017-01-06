``audio-feeder`` is a Flask-based web-app that hosts your audiobooks (or other audio content) as RSS feeds compatible with podcatchers.

Installation
============
Currently, there is no installer that will install things "correctly", so you should look into the proper way to deploy this web app. In 'development mode', you can install it using these steps:

- Download the source code, ``cd`` into the extracted directory.
- In your virtualenv, run ``pip install .``
- Run ``audio-feeder install`` - this should create a basic ``{{CONFIG}}`` directory in ``/etc/audio_feeder`` or ``~/.config/audio_feeder``
- Modify the configuration files in ``{{CONFIG}}/config.yml`` as desired.
- Modify the templates and CSS files as desired.
- Create a symbolic link to your audiobooks directory under ``{{CONFIG}}/static/media/`` (e.g. ``~/.config/audio_feeder/static/media/audiobooks``) - we'll call this ``{{AUDIOBOOKS}}``.
- Run ``audio-feeder update {{AUDIOBOOKS}}`` to pull metadata from Google Books (for a large number of audiobooks, you may need to get a `Google API key <https://developers.google.com/maps/documentation/javascript/get-api-key>`_, which should be entered in your ``config.yml`` page under ``google_api_key``).
- Run the server with ``audio-feeder run``
- Visit your page at ``localhost:9090`` (default value). *Note:* You should specify your computer's specific IP address if you are planning on serving your audiobooks directly to a phone or device over wifi.

If you add more audiobooks to your audiobook path, run ``audio-feeder update {{AUDIOBOOKS}}`` again and restart the application.

Note
=====
Version 0.1.0 is a very rough initial cut, and if you're looking for something easy to use out of the box, you may have to wait a bit longer. The odd choice of using YAML files as a pseudo-database is *not* intended to be permanent, and these will be replaced with a proper database soon.

Dependencies
============
The following dependencies are required for installation, and will be installed if missing when installed through `pip`:

- ``Flask``
- ``ruamel.yaml``
- ``qrcode``
- ``Pillow``
- ``requests``
- ``jinja2``
- ``click``
- ``progressbar2``

To run the test suite, ``pytest`` is also required.

License
=======
All images and documentation contained herein are licensed under `CC-0 <https://creativecommons.org/publicdomain/zero/1.0/>`_.

The code is released under the `Apache 2.0 <https://www.apache.org/licenses/LICENSE-2.0>`_ license.

Contributing
============
Pull requests and issues are more than welcome. Please be aware that your contributions will be released under the licenses stated above. If you are not comfortable with that, please do not make a pull request.
