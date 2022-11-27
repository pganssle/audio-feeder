"""
Command line scripts
"""
import pathlib

import click


@click.group()
def cli():
    """
    Options are:
        run
        update
        version
    """


@cli.command()
def version():
    from . import __version__

    print(f"audio_feeder version: {__version__.VERSION}")


@cli.command()
@click.option("--host", default=None, help="The host to run the application on.")
@click.option(
    "-p", "--port", default=None, type=int, help="The port to run the application on."
)
@click.option(
    "-c",
    "--config",
    default=None,
    type=str,
    help="A YAML config file to use for this particular run.",
)
@click.option("--profile", is_flag=True, help="Runs with profiler on.")
def run(host, port, config, profile):
    """
    Runs the flask application, starting the web page with certain configuration
    options specified.
    """
    from .app import create_app
    from .config import init_config, read_from_config

    kwargs = {}
    if host is not None:
        kwargs["base_host"] = host

    if port is not None:
        kwargs["base_port"] = port

    init_config(config_loc=config, **kwargs)

    app = create_app()
    app.static_folder = read_from_config("static_media_path")

    if profile:
        from werkzeug.middleware.profiler import ProfilerMiddleware

        profile_dir = pathlib.Path.cwd() / ".profile"
        profile_dir.mkdir(exist_ok=True)
        app.config["PROFILE"] = True
        app.wsgi_app = ProfilerMiddleware(app.wsgi_app, profile_dir=".profile")
        debug = True
    else:
        debug = False

    app.run(
        host=read_from_config("base_host"),
        port=read_from_config("base_port"),
        debug=debug,
    )


@cli.command()
@click.option(
    "-t",
    "--content-type",
    type=str,
    default="books",
    help=(
        "The type of content to load from the directories. Options:"
        + "  b / books: Audiobooks"
    ),
)
@click.option(
    "-r",
    "--reload-metadata",
    is_flag=True,
    help="Passed if metadata from all sources should be reloaded if present.",
)
@click.argument("path", metavar="PATH", type=str, required=True)
def update(content_type, reload_metadata, path):
    """
    Add a specific path to the databases, loading all content and updating the
    database where necessary.

    The path at PATH will be recursively searched for data.
    """
    import typing

    from progressbar import ETA, Bar, ProgressBar, Timer

    from . import updater as afu

    _T = typing.TypeVar("_T", bound=typing.Iterable)

    def pbar(msg: str) -> typing.Callable[[_T], _T]:
        return ProgressBar(widgets=[msg, " ", Bar(), " ", Timer(), " ", ETA()])

    afu.update(
        content_type=content_type,
        path=path,
        progress_bar=pbar("Loading book metadata:"),
    )


@cli.command()
@click.option(
    "-c",
    "--config-dir",
    type=str,
    default=None,
    help=("The configuration directory to use as a base for all"),
)
@click.option(
    "-n",
    "--config-name",
    type=str,
    default=None,
    help="The name to use for the configuration file. Default is config.yml",
)
def install(config_dir, config_name):
    """
    Installs the feeder configuration and populates the initial file structures
    with the default package data.
    """
    import os
    import warnings

    from . import config, resources

    # Assign a configuration directory
    if config_dir is None:
        for config_dir in config.config_dirs(with_pwd=False):
            if not config_dir.exists():
                try:
                    os.makedirs(config_dir)
                    break
                except Exception as e:
                    warnings.warn(
                        f"Failed to make directory {config_dir}; "
                        + f"failed with error:\n{e}",
                        RuntimeWarning,
                    )
            else:
                break
        else:
            raise IOError("Failed to create any configuration directories.")

    config_name = config_name or config.CONFIG_NAMES[0]
    config_loc = os.path.join(config_dir, config_name)

    # Initialize the configuration
    config.init_config(config_loc)
    config_obj = config.get_configuration()

    # Write the configuration to file
    config_obj.to_file(config_loc)

    # Create the directories that need to exist, if they don't already
    make_dir_entries = ("static_media_path",)  # Absolute paths

    make_dir_directories = [config_obj[x] for x in make_dir_entries]
    static_paths = [
        os.path.join(config_obj.static_media_path, config_obj[x])
        for x in (
            "site_images_loc",
            "cover_cache_path",
            "qr_cache_path",
            "media_cache_path",
        )
    ]  # Relative paths

    make_dir_directories += static_paths
    make_dir_directories.append(pathlib.Path(config_obj["database_loc"]).parent)

    mkdir_ordered = sorted(
        map(pathlib.Path, make_dir_directories), key=pathlib.Path.absolute
    )

    for i, c_dir in enumerate(mkdir_ordered):
        try:
            c_dir.mkdir(exist_ok=True)
        except FileNotFoundError:
            # If we have created one of the parents of this directory, but
            # some parents are missing, we should create the intermediates.
            #
            # Because the list is sorted by absolute path, we only have to
            # search up to the point in the list we've already reached, and
            # we are more likely to find it towards the *end* of that list
            # than the beginning, so we'll search in reverse.
            for possible_parent in mkdir_ordered[max(0, i - 1) :: -1]:
                if possible_parent in c_dir.parents:
                    c_dir.mkdir(parents=True)
                    break
            else:
                raise

    # Copy all package data as appropriate
    resources.update_resource(
        "audio_feeder.data.site", pathlib.Path(config_obj["static_media_path"])
    )


@cli.group()
def find_missing_books():
    """
    For books where the automatic metadata loader failed, this will load a YAML
    file of books which may need manual attention.
    """
    pass


@find_missing_books.command()
@click.option(
    "-yo",
    "--overwrite",
    is_flag=True,
    help='Automatically answer yes to "overwrite" prompt.',
)
@click.option(
    "-o",
    "--output",
    type=str,
    default="missing.yml",
    help="Where to load the dictionary mapping entry IDs to names and values.",
)
def load(overwrite, output):
    """
    Load the books from the current database that are missing into an optionally
    specified YAML file.
    """
    import os

    import yaml

    from . import database_handler as dh

    if os.path.exists(output) and not overwrite:
        click.confirm(f"Do you want to overwrite {output}?", abort=True)

    print("Loading database")
    books_table = dh.get_database_table("books")

    # Retrieve all the books with no metadata sources
    print("Searching for books with missing metadata")
    books_no_metadata = {}
    for book_id, book_obj in books_table.items():
        if not book_obj.metadata_sources:
            books_no_metadata[book_id] = book_obj

    # For each book we want to save three pieces of information:
    book_data = ["id", "authors", "title"]

    # And we want to provide space for the following IDs:
    book_id_slots = ["isbn", "isbn13", "google_id", "goodreads_id"]

    books_out = []
    print("Preparing output")
    for book_id, book_obj in books_no_metadata.items():
        # Doing this as a list of dictionaries to maintain the order and make
        # it look nice when humans are interacting with it.
        book_out = [
            {book_field: getattr(book_obj, book_field)} for book_field in book_data
        ]
        book_out += [
            {book_field: getattr(book_obj, book_field, None)}
            for book_field in book_id_slots
        ]

        books_out.append(book_out)

    books_out = sorted(
        books_out, key=lambda x: x[book_data.index("authors")]["authors"][0]
    )

    print(f"Writing output to {output}")
    with open(output, "w") as f:
        yaml.dump(books_out, stream=f, default_flow_style=False)


@find_missing_books.command("update")
@click.option(
    "-i",
    "--input",
    type=str,
    default="missing.yml",
    help="Where to load the missing books from.",
)
def update_missing_books(**kwargs):
    import yaml

    from . import database_handler as dh

    input_fpath = kwargs["input"]

    with open(input_fpath, "r") as f:
        missing_db = yaml.safe_load(f)

    # Fields we're expecting to find
    book_id_slots = ["isbn", "isbn13", "google_id", "goodreads_id"]

    print(f"Loading missing book data from {input_fpath}")
    books_in = {}
    for book_in in missing_db:
        # These are a list of dictionaries, for human readability reasons.
        book_dict = {}
        for item in book_in:
            book_dict.update(item)

        # Load anything which has a real value for one of the IDs.
        if any(book_dict[id_slot] for id_slot in book_id_slots):
            books_in[book_dict["id"]] = book_dict

    print("Loading book table database")
    db = dh.load_database()
    books_table = db["books"]

    load_if_avail = ["authors", "title"] + book_id_slots

    for book_id, book_dict in books_in.items():
        book_obj = books_table[book_id]

        for field in load_if_avail:
            v = book_dict.get(field, None)
            if v:
                setattr(book_obj, field, v)

        db["books"][book_id]

    print("Saving book database")
    dh.save_database(db)


@cli.command()
@click.argument(
    "db_in",
    metavar="DB_IN",
    type=click.Path(path_type=pathlib.Path, exists=True),
    required=True,
)
@click.argument(
    "db_out",
    metavar="DB_OUT",
    type=click.Path(path_type=pathlib.Path, exists=False),
    required=True,
)
def convert_db(db_in: pathlib.Path, db_out: pathlib.Path):
    """
    Take an old YAML-style "database" and convert it to sqlite3
    """

    if db_out.exists():
        raise ValueError(f"Output path already exists: {db_out}")

    from audio_feeder import database_handler as dh

    old_db = dh.load_database(db_in)
    dh.save_database(old_db, db_out)
