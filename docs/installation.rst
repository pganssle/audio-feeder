Installation
============

The easiest way to deploy ``audio-feeder`` is with Docker, using the
docker-compose configuration in the `audio_feeder_docker
<https://github.com/pganssle/audio_feeder_docker>`_ repository. If you'd rather
not use Docker, or you just want to try it out on your own computer, you can
install the Python package directly instead; see `Installing the Python
package`_.

Docker
------

The ``audio_feeder_docker`` configuration runs the app under ``gunicorn`` in
one container, with ``nginx`` in another container serving the static files
(including the audio files themselves) and forwarding everything else to the
app, on port 8080. Its README has the full instructions, which in outline are:

1. Clone the repository, copy ``env_template`` to ``.env`` and set
   ``AUDIOBOOK_DIR`` in it to the directory containing your audiobooks. The
   other variables are the directories on the host where the database, the
   static files and the rendered feeds are kept, under ``/data/audio_feeder``
   by default.
2. Copy ``config/audio_feeder/config.yml.example`` to
   ``config/audio_feeder/config.yml``. This has to exist before the container
   is first started, because otherwise Docker creates an empty directory in its
   place.
3. Run ``docker-compose build`` to build the image, then
   ``./install_audio_feeder.sh``, which runs ``audio-feeder install`` (see
   :doc:`usage`) in the container to set up the configuration directory, then
   ``docker-compose up -d`` to start the server.
4. Load your books into the database with ``docker-compose run audio_feeder
   audio-feeder update``, or by visiting the ``/update`` URL of the running
   server. Optionally, ``./install.sh`` installs a ``systemd`` timer that does
   this every three hours.

The configuration file is ``config/audio_feeder/config.yml`` in your checkout
of ``audio_feeder_docker``, which is mounted at ``/etc/audio_feeder/config.yml``
in the container. That's the file to edit to change any of the settings in
:doc:`configuration`, after which you need to restart the container with
``docker-compose restart audio_feeder``, since the configuration is only read
when the app starts. At the very least, you'll want to set ``base_host`` to an
address of the host that your phone can reach, and ``base_port`` to 8080 (the
example configuration already does the latter), since these are used to build
the URLs in the feeds.

Your audiobooks are mounted at ``static/media/audiobooks`` in the container,
which means that they all show up in an ``audiobooks`` folder of the media
directory; see :doc:`usage` for how the books in it should be laid out. The
rest of this documentation describes running ``audio-feeder`` directly, so
wherever it says to run an ``audio-feeder`` command, run it in the container
instead, e.g. ``docker-compose run audio_feeder audio-feeder update``. You don't
need ``audio-feeder run``, since the container runs the app under ``gunicorn``.

Installing the Python package
-----------------------------

``audio-feeder`` is published on PyPI, so you can install it with ``pip``,
preferably in a virtual environment:

.. code-block:: console

    $ python -m venv venv
    $ source venv/bin/activate
    $ pip install audio-feeder

If you only need the ``audio-feeder`` command, you can instead install it as a
tool with `uv <https://docs.astral.sh/uv/>`_, which puts the command on your
``PATH`` with an isolated environment of its own:

.. code-block:: console

    $ uv tool install audio-feeder

To install the latest development version, install from the git repository
instead:

.. code-block:: console

    $ pip install git+https://github.com/pganssle/audio-feeder

Either way, ``audio-feeder --help`` should then list the commands described in
:doc:`cli`. Next, follow :doc:`usage` to create a configuration directory, add
your books and start the server. The configuration file is ``config.yml`` in
the directory that ``audio-feeder install`` creates, and
:ref:`config-location` describes how ``audio-feeder`` finds it.

ffmpeg
~~~~~~

In addition to the Python dependencies, which are installed automatically,
``audio-feeder`` needs `ffmpeg <https://ffmpeg.org/>`_ on your ``PATH``, built
with at least the ``aac`` codec. The Docker image already includes it, and
most Linux distributions package a suitable build, e.g. ``apt install ffmpeg``
or ``pacman -S ffmpeg``.

Strictly speaking, the server starts and the database can be updated without
it, but ``ffprobe`` is used to read the durations and chapters of the audio
files for every feed, and ``ffmpeg`` to generate the rendered feeds, so without
it none of the feeds work.
