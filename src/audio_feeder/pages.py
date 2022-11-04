#! /usr/bin/env python3

import functools
import html
import itertools as it
import logging
import os
import textwrap
import threading
import typing
from datetime import datetime, timezone

import flask
from flask import Blueprint, request
from jinja2 import Template

from audio_feeder import database_handler as dh
from audio_feeder import page_generator as pg
from audio_feeder import rss_feeds as rf
from audio_feeder.config import init_config, read_from_config
from audio_feeder.resolver import get_resolver

root = Blueprint("root", __name__)

###
# Pages


@root.route("/")
def main_index():
    """
    The base index - for now this redirects to the audiobooks.
    """
    return flask.redirect(flask.url_for("root.books"))


@functools.lru_cache(None)
def _book_entry_cache():
    return {}


@functools.lru_cache
def _book_nav_generator(nav_len: int, endpoint: str) -> pg.NavGenerator:
    return pg.NavGenerator(nav_len, flask.url_for(endpoint))


def _clear_book_caches():
    _book_entry_cache.cache_clear()
    _book_nav_generator.cache_clear()


@root.route("/books")
def books():
    """
    The main page for listing audiobooks
    """
    sort_args = get_sortable_args(request.args)

    # Retrieve or populate the entry cache.
    entry_cache = _book_entry_cache()

    if "base" not in entry_cache:
        # Get the list of entries (SELECT * from entries WHERE type == 'book')
        entries = [
            entry_obj
            for entry_obj in dh.get_database_table("entries").values()
            if entry_obj.type == "Book"
        ]

        entry_cache["base"] = entries
    else:
        entries = entry_cache["base"]

    nav_generator = _book_nav_generator(len(entries), request.endpoint)

    # Retrieve or populate the specific sort cache
    arg_sort = tuple(sorted(sort_args.items()))
    if arg_sort not in entry_cache:
        entries = get_sorted_entries(entries, sort_args)
        entry_cache[arg_sort] = entries
    else:
        entries = entry_cache[arg_sort]

    # Do the pagination
    entry_page = get_paged_entries(entries, sort_args)

    nav_list = nav_generator.get_pages(sort_args)
    max_page = len(nav_list) - 1
    page = min(sort_args["page"], max_page)
    if nav_list:
        first_index = nav_list[0].url or request.path
        prev_index = nav_list[max((page - 1, 0))].url
        next_index = nav_list[min((page + 1, max_page))].url
        final_index = nav_list[-1].url
    else:
        first_index = None
        prev_index = None
        next_index = None
        final_index = None

    resolver = get_resolver()
    site_images = resolver.resolve_static(read_from_config("site_images_loc"))

    page_data = {
        "entries": get_rendered_entries(entry_page),
        "nav_list": nav_generator.get_pages(sort_args),
        "first_index": first_index,
        "final_index": final_index,
        "prev_index": prev_index,
        "next_index": next_index,
        "pagetitle": f"Books: Page {page+1} of {len(nav_list)}",
        "site_images_url": site_images.url,
        "default_cover": os.path.join(site_images.url, "default_cover.svg"),
        "sort_options": get_sort_options(),
        "sort_args": sort_args,
        "stylesheet_links": get_css_links(),
        "favicon": None,
    }

    # Apply the template
    t = get_list_template()
    return t.render(page_data)


@root.route("/rss/<int:e_id>.xml")
def rss_feed(e_id):
    """
    Generates an RSS feed.

    The template will be passed the following variables:
        - ``channel_title``
        - ``channel_desc``
        - ``channel_link``
        - ``build_date``
        - ``pub_date``
        - ``author``
        - ``cover_image``
    """

    entry_table = dh.get_database_table("entries")
    if e_id not in entry_table:
        flask.abort(404)

    entry_obj = entry_table[e_id]
    data_obj = dh.get_data_obj(entry_obj)

    # Render the main "feed-wide" portions of this
    renderer = get_renderer(rss_renderer=True)
    rendered_page = renderer.render(entry_obj, data_obj)

    channel_title = rendered_page["name"]
    channel_desc = rendered_page["description"]

    build_date = entry_obj.last_modified
    pub_date = entry_obj.date_added

    author = rendered_page["author"]

    cover_image = entry_obj.cover_images[0] if entry_obj.cover_images else None
    if cover_image is not None:
        cover_image = get_resolver().resolve_static(cover_image).url
        cover_image = cover_image.replace("[", "%5B")
        cover_image = cover_image.replace("]", "%5D")

    # This gives me the "items" list
    feed_items = rf.load_feed_items(entry_obj)
    payload = {
        "channel_title": channel_title,
        "channel_desc": channel_desc,
        "channel_link": request.path,
        "build_date": build_date,
        "pub_date": pub_date,
        "author": author,
        "cover_image": cover_image,
        "items": feed_items,
    }

    payload = {k: rf.wrap_field(v) for k, v in payload.items()}

    t = get_feed_template()

    return t.render(payload)


UPDATE_LOCK = threading.Lock()
UPDATE_IN_PROGRESS: bool = False
UPDATE_OUTPUT: typing.Sequence[str] = []


def _log_update_output(update: str) -> None:
    global UPDATE_OUTPUT
    if UPDATE_OUTPUT is None:
        UPDATE_OUTPUT = []

    typing.cast(typing.MutableSequence[str], UPDATE_OUTPUT).append(update)
    logging.info(update)


def _clear_update_output() -> None:
    global UPDATE_OUTPUT
    typing.cast(typing.MutableSequence[str], UPDATE_OUTPUT).clear()


def _update_db() -> None:
    """
    Trigger an update to the database.
    """

    from . import resolver, updater

    _log_update_output("Updating audiobooks from all directories.")
    path = resolver.Resolver().resolve_media(".").path

    book_updater = updater.BookDatabaseUpdater(path)

    _log_update_output("Loading existing database")
    db = dh.load_database()

    ops = [
        (book_updater.update_db_entries, "Updating databse entries."),
        (book_updater.assign_books_to_entries, "Assigning books to entries"),
        (book_updater.update_book_metadata, "Updating book metadata"),
        (book_updater.update_author_db, "Updating author db"),
        (book_updater.update_cover_images, "Updating cover images"),
    ]

    for op, log_output in ops:
        _log_update_output(log_output)
        op(db)
        dh.save_database(db)

    _clear_book_caches()
    _log_update_output("Reloading database")
    dh.get_database(refresh=True)

    _clear_update_output()

    global UPDATE_IN_PROGRESS
    UPDATE_IN_PROGRESS = False


@root.route("/update_status")
def update_status():
    if not UPDATE_IN_PROGRESS:
        return flask.redirect(flask.url_for("root.books"))

    html_template = textwrap.dedent(
        """
    <html>
        <head>
            <title>Updating audiobook database</title>
            <meta http-equiv="refresh" content="1">
        </head>
        <body>
            <b>Audiobook database update in progress, current status:<b><br/>
            <br/>
            <tt>
            {logs}
            </tt>
            <br/>
            <br/>
            This page will refresh every 5 seconds until done, at which point
            you will be redirected back to <a href="{root_url}">the main page.</a>
        </body>
    </html>"""
    )

    return html_template.format(
        logs="<br/>\n".join(UPDATE_OUTPUT), root_url=flask.url_for("root.books")
    )


@root.route("/update")
def update():
    global UPDATE_IN_PROGRESS
    with UPDATE_LOCK:
        if not UPDATE_IN_PROGRESS:
            background_thread = threading.Thread(target=_update_db, daemon=True)
            UPDATE_IN_PROGRESS = True
            background_thread.start()

        return flask.redirect(flask.url_for("root.update_status"))


###
# Functions (probably want to move most of these to page_generator)
def get_rendered_entries(entry_list):
    renderer = get_renderer()

    o = [
        renderer.render(entry_obj, data_obj)
        for entry_obj, data_obj, auth_objs in entry_list
    ]

    return o


def get_paged_entries(entry_list, sort_args):
    per_page = sort_args["perPage"]
    page = sort_args["page"]
    start_loc = page * per_page
    end_loc = start_loc + per_page

    return entry_list[start_loc:end_loc]


def get_sorted_entries(entry_list, sort_args):
    """
    Retrieve a list of entries, sorted according to the sort arguments.
    """
    order_by = sort_args["orderBy"]
    sort_ascending = sort_args["sortAscending"]

    # Default sort order is author
    if order_by == "author":
        sort_order = ["author", "series", "title", "date_added", "last_modified"]
    elif order_by == "title":
        sort_order = ["title", "author", "series", "date_added", "last_modified"]
    elif order_by == "date_added":
        sort_order = ["date_added", "last_modified", "author", "series", "title"]
    elif order_by == "last_modified":
        sort_order = ["last_modified", "date_added", "author", "series", "title"]

    def _sort_key(el_e):
        ent_obj, data_obj, auth_objs = el_e
        keys = {}

        keys["author"] = [auth_obj.sort_name or auth_obj.name for auth_obj in auth_objs]

        keys["title"] = data_obj.title
        if data_obj.series_name:
            keys["series"] = (data_obj.series_name, data_obj.series_number)
        else:
            keys["series"] = ("", 0)

        keys["date_added"] = ent_obj.date_added
        keys["last_modified"] = ent_obj.last_modified

        # Replace None with an empty string
        return tuple(keys[k] or "" for k in sort_order)

    return sorted(
        get_entry_objects(entry_list), key=_sort_key, reverse=not sort_ascending
    )


def get_entry_objects(entry_list):
    """
    Retrieve a list of (entry, data_obj) pairs.
    """
    # Grouping these together like this just to minimize the number of calls
    # to get_database_table.
    author_table = dh.get_database_table("authors")

    for table_name, group in it.groupby(entry_list, key=lambda x: x.table):
        table = dh.get_database_table(table_name)

        for entry_obj in group:
            data_obj = table[entry_obj.data_id]

            # Retrieve the author objects as well
            author_objs = [author_table[author_id] for author_id in data_obj.author_ids]

            yield (entry_obj, data_obj, author_objs)


@functools.lru_cache(None)
def get_sort_options() -> typing.Mapping[str, str]:
    return {
        "Date Added": "date_added",
        "Author": "author",
        "Title": "title",
        "Last Modified": "last_modified",
    }


def get_sortable_args(args):
    # Sort field
    sort_options = tuple(get_sort_options().values())
    order_by = args.get("orderBy", None)

    if order_by is not None and order_by not in sort_options:
        logging.error(
            "Order by option {} invalid, ".format(order_by)
            + "must be one of: {}".format(",".join(sort_options))
        )
        order_by = None

    if order_by is None:
        order_by = sort_options[0]

    # Ascending / descending
    if order_by in ("date_added", "last_modified"):
        default_ascending = "False"
    else:
        default_ascending = "True"

    sort_order = args.get("sortAscending", default_ascending).lower()
    sort_ascending = sort_order != "false"

    # Items per page
    per_page_dflt = 25
    per_page = None
    if "perPage" in args:
        try:
            per_page_arg = args.get("perPage")
            per_page = int(per_page_arg)
        except ValueError:
            logging.error(
                "Number per page {} ".format(perPage) + "must be convertable to int."
            )

    per_page = per_page or per_page_dflt

    # Current page location
    page = int(args.get("page", 0))

    args = {
        "sortAscending": sort_ascending,
        "orderBy": order_by,
        "perPage": per_page,
        "page": page,
    }

    return args


def get_list_template():
    template = getattr(get_list_template, "_template", None)
    if template is None:
        template = _get_template("pages_templates_loc", "list.tpl")
        get_list_template._template = template

    return template


def get_feed_template():
    template = getattr(get_feed_template, "_template", None)
    if template is None:
        template = _get_template("rss_templates_loc", "rss_feed.tpl")
        get_feed_template._template = template

    return get_feed_template._template


def _get_template(loc_entry, template_name):
    template_loc = read_from_config(loc_entry)
    template_loc = os.path.join(template_loc, template_name)

    with open(template_loc, "r") as f:
        template = Template(f.read())

    return template


def get_renderer(rss_renderer=False):
    renderer = getattr(get_renderer, "_renderer", {})
    if rss_renderer not in renderer:
        resolver = get_resolver()

        kwargs = {}
        if rss_renderer:
            kwargs["entry_templates_config"] = "rss_entry_templates_loc"

        renderer[rss_renderer] = pg.EntryRenderer(resolver=resolver, **kwargs)

        get_renderer._renderer = renderer

    return renderer[rss_renderer]


def get_css_links():
    resolver = get_resolver()
    css_loc = read_from_config("css_loc")
    css_locs = [
        os.path.join(css_loc, css_file)
        for css_file in read_from_config("main_css_files")
    ]

    css_paths = [resolver.resolve_static(css_relpath).url for css_relpath in css_locs]

    return css_paths
