- Now available: rendered feeds! This adds alternate feeds for files generated from the files as they exist on disk using ffmpeg (the generated files go into a media cache on disk and are generated when the RSS feed is downloaded). The available types of feed are:

    - Single file: In single file mode, all input files are merged into one big file, with chapter information if it's available (defaulting to considering each separate file a chapter).
    - Chapters: If chapter information is available, each chapter is a separate entry in the feed.
    - Segmented: This assumes that you want files broken up into duration ~60 minutes, and tries to accommodate that as best as possible. The segmenting algorithm recombines the existing files along chapter or file boundaries in such a way as to minimize the overall deviation from "60 minutes per file". It is slightly biased towards longer files, so it will prefer to create 1 90 minute file rather than 2 45 minute files, etc.

A side-effect of this change is that file metadata is stored in the database now, which will take some time to add when first loading a large number of audiobooks. This also enables us to have chapter information in the RSS feeds.
