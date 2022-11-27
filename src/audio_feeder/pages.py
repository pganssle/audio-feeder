#! /usr/bin/env python3

import functools
import itertools as it
import logging
import os
import textwrap
import threading
import typing
from datetime import datetime, timezone

import flask
from flask import Blueprint, Response, request
from jinja2 import Template

from audio_feeder import _object_types as ot
from audio_feeder import database_handler as dh
from audio_feeder import media_renderer as mr
from audio_feeder import object_handler as oh
from audio_feeder import page_generator as pg
from audio_feeder import resources
from audio_feeder import rss_feeds as rf
from audio_feeder.config import read_from_config
from audio_feeder.file_location import FileLocation
from audio_feeder.resolver import get_resolver

from . import cache_utils, updater
from ._db_types import ID, TableName

root = Blueprint("root", __name__)

###
# Pages


@root.route("/")
def main_index():
    """
    The base index - for now this redirects to the audiobooks.
    """
    return flask.redirect(flask.url_for("root.books"))


@cache_utils.register_function_cache("books")
@functools.lru_cache(None)
def _book_entry_cache():
    return {}


@cache_utils.register_function_cache("books")
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
        "pagetitle": f"Books: Page {page} of {max_page}",
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


def _render_rss_feed(entry_obj: oh.Entry, data_obj: ot.SchemaObject, feed_items) -> str:
    # Render the main "feed-wide" portions of this
    renderer = get_renderer(rss_renderer=True)
    rendered_page = renderer.render(entry_obj, data_obj)

    channel_title = rendered_page["name"]
    channel_desc = rendered_page["description"]

    now = datetime.now(timezone.utc)
    build_date = rf.format_datetime(entry_obj.last_modified or now)
    pub_date = rf.format_datetime(entry_obj.date_added or now)

    author = rendered_page["author"]

    cover_image = entry_obj.cover_images[0] if entry_obj.cover_images else None
    if cover_image is not None:
        cover_image_url = get_resolver().resolve_static(os.fspath(cover_image)).url
        cover_image_url = cover_image_url.replace("[", "%5B")
        cover_image_url = cover_image_url.replace("]", "%5D")
    else:
        cover_image_url = None

    # This gives me the "items" list
    payload = {
        "channel_title": channel_title,
        "channel_desc": channel_desc,
        "channel_link": request.url,
        "build_date": build_date,
        "pub_date": pub_date,
        "author": author,
        "cover_image": cover_image_url,
        "items": feed_items,
    }

    payload = {k: rf.wrap_field(v) for k, v in payload.items()}

    t = get_feed_template()

    return t.render(payload)


@root.route("/rss/derived/<int:e_id>-<string:mode>.xml")
def derived_rss_feed(e_id, mode):
    """
    Generates RSS feeds for the different derived feed modes.

    Allowed modes are:
        - singlefile
        - chapters
        - segmented
    """

    try:
        render_mode = mr.RenderModes(mode.upper())
    except ValueError:
        flask.abort(404)

    entry_table = dh.get_database_table(TableName("entries"))

    if e_id not in entry_table:
        flask.abort(404)

    entry_obj = entry_table[e_id]

    resolver = get_resolver()

    media_loc = resolver.resolve_media_cache(f"{e_id}-{render_mode.lower()}")
    media_path = media_loc.path

    renderer = mr.Renderer(media_path, entry_obj, mode=render_mode)
    renderer.trigger_rendering()

    # If no rendering was necessary, we redirect back to the default feed.
    if renderer.is_default():
        return flask.redirect(f"/rss/{e_id}.xml", code=302)

    renderer.update_access_time()

    if not renderer.rss_file.exists():
        file_metadata = renderer.read_file_metadata()
        file_metadata_loc = {
            FileLocation(
                fpath,
                url_base=media_loc.url,
                path_base=renderer.media_path,
            ): value
            for fpath, value in file_metadata.items()
        }

        feed_items = rf.feed_items_from_metadata(
            entry_obj,
            renderer.data_obj,
            audio_dir=renderer.media_path,
            file_metadata=file_metadata_loc,
            mode=mode,
            resolver=resolver,
        )

        rss_file_contents = _render_rss_feed(entry_obj, renderer.data_obj, feed_items)
        renderer.rss_file.write_text(rss_file_contents)
    else:
        rss_file_contents = renderer.rss_file.read_text()
    return Response(renderer.rss_file.read_text(), mimetype="application/xml")


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

    feed_items = rf.load_feed_items(entry_obj)

    return Response(
        _render_rss_feed(entry_obj, data_obj, feed_items),
        mimetype="application/xml",
    )


@root.route("/chapter-data/<int:e_id>-<string:guid>.json")
def chapter_data(e_id: int, guid: str) -> Response:
    resolver = get_resolver()
    mode = request.args.get("mode", None)

    entry_table = dh.get_database_table(TableName("entries"))

    if e_id not in entry_table:
        logging.error("ID not in entry table: %s", e_id)
        flask.abort(404)

    entry_obj = typing.cast(oh.Entry, entry_table[ID(e_id)])
    if mode is not None:
        render_mode = mr.RenderModes(mode.upper())
        media_loc = resolver.resolve_media_cache(f"{e_id}-{render_mode.lower()}")
        media_path = media_loc.path

        assert media_path is not None
        renderer = mr.Renderer(media_path, entry_obj, render_mode)

        if renderer.is_default():
            flask.redirect(request.path)

        file_metadata = renderer.read_file_metadata()
        for file, (file_info, file_guid) in file_metadata.items():
            if guid == file_guid:
                break
        else:
            logging.error(
                "No file found with guid %s for entry %s in mode %s", guid, e_id, mode
            )
            flask.abort(404)

    else:
        assert entry_obj.file_metadata
        assert entry_obj.file_hashes
        for file, file_guid in entry_obj.file_hashes.items():
            if file_guid == guid:
                break
        else:
            logging.error("No file found with guid %s for entry %s", guid, e_id)
            flask.abort(404)

        if file not in entry_obj.file_metadata:
            logging.error("No metadata found for %s-%s", guid, e_id)
            flask.abort(404)

        file_info = entry_obj.file_metadata[file]

    assert file_info.chapters
    return Response(
        rf.generate_chapter_json(file_info.chapters), mimetype="application/json"
    )


###
# Database updates
UPDATE_LOCK = threading.Lock()


@root.route("/update_status")
def update_status():
    if not updater.UPDATE_IN_PROGRESS:
        return flask.redirect(flask.url_for("root.books"))

    refresh_time = 1
    html_template = textwrap.dedent(
        """
    <html>
        <head>
            <title>Updating audiobook database</title>
            <meta http-equiv="refresh" content="{refresh_time}">
        </head>
        <body>
            <b>Audiobook database update in progress, current status:<b><br/>
            <br/>
            <tt>
            {logs}
            </tt>
            <br/>
            <br/>
            This page will refresh every {refresh_time} seconds until done, at which
            point you will be redirected back to <a href="{root_url}">the main page.</a>
        </body>
    </html>"""
    )

    return html_template.format(
        logs="<br/>\n".join(updater.UPDATE_OUTPUT),
        root_url=flask.url_for("root.books"),
        refresh_time=refresh_time,
    )


@root.route("/update")
def update():
    with UPDATE_LOCK:
        if not updater.UPDATE_IN_PROGRESS:
            updater.UPDATE_IN_PROGRESS = True
            background_thread = threading.Thread(target=updater.update, daemon=True)
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


@cache_utils.register_function_cache("misc")
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
            f"Order by option {order_by} invalid, "
            + f"must be one of: {','.join(sort_options)}"
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
            logging.error("Number per page %s must be convertable to int.", perPage)

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


@functools.cache
def get_list_template() -> Template:
    template = _get_template(
        "pages_templates_loc",
        "list.tpl",
        resource_default="audio_feeder.data.templates.pages",
    )

    return template


@functools.cache
def get_feed_template() -> Template:
    return _get_template(
        "rss_templates_loc",
        "rss_feed.tpl",
        resource_default="audio_feeder.data.templates.rss",
    )


def _get_template(
    loc_entry: str, template_name: str, resource_default: typing.Optional[str] = None
) -> Template:
    template_loc = read_from_config(loc_entry) / template_name

    if template_loc.exists():
        return Template(template_loc.read_text())
    elif resource_default is not None:
        return Template(resources.get_text_resource(resource_default, template_name))
    else:
        raise FileNotFoundError(f"Could not find template: {template_loc}")


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


@functools.cache
def get_css_links() -> typing.Sequence[str]:
    resolver = get_resolver()
    css_loc = read_from_config("css_loc")
    css_locs: typing.MutableSequence[str] = []
    if not read_from_config("disable_default_css"):
        static_path = read_from_config("static_media_path")
        default_loc = resolver.resolve_static(css_loc)
        default_path = default_loc.path
        assert default_path is not None
        resources.update_resource("audio_feeder.data.css", default_path)
        css_locs.extend(
            os.fspath(fpath.relative_to(static_path))
            for fpath in default_path.rglob("*.css")
        )

    css_locs.extend(
        (
            os.path.join(css_loc, css_file)
            for css_file in read_from_config("extra_css_files")
        )
    )

    css_paths = [resolver.resolve_static(css_relpath).url for css_relpath in css_locs]

    return css_paths
