Version 0.6.0
=============

- Now available: rendered feeds! This adds alternate feeds for files generated from the files as they exist on disk using ``ffmpeg`` (the generated files go into a media cache on disk and are generated when the RSS feed is downloaded). The available types of feed are:

    - Single file: In single file mode, all input files are merged into one big file, with chapter information if it's available (defaulting to considering each separate file a chapter).
    - Chapters: If chapter information is available, each chapter is a separate entry in the feed.
    - Segmented: This assumes that you want files broken up into duration ~60 minutes, and tries to accommodate that as best as possible. The segmenting algorithm recombines the existing files along chapter or file boundaries in such a way as to minimize the overall deviation from "60 minutes per file". It is slightly biased towards longer files, so it will prefer to create 1 90 minute file rather than 2 45 minute files, etc.

  A side-effect of this change is that file metadata is stored in the database now, which will take some time to add when first loading a large number of audiobooks. This also enables us to have chapter information in the RSS feeds.

- Added a test server script for easy manual debugging and testing.

- Changed config directory specification. You can now set the environment variable ``AF_CONFIG_DIR`` to specify exactly where your configuration comes from. Whether or not the current working directory is in the search path is also now context dependent.

- Removed ``schema.yml`` in favor of defining the schema types in ``object_handler.py``

- Updated the ``audio-feeder install`` script to use ``importlib.resources`` and made sure that it can be run a second time to update the install base.

- "Updating database" status now cleared if the database update fails.

- Updated books pagination to consistently use a zero-based index.

