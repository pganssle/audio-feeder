#! /usr/bin/env python3

import enum
import functools
import itertools as it
import logging
import os
import re
import textwrap
import threading
from collections.abc import (
    Callable,
    Iterable,
    Mapping,
    MutableSequence,
    Sequence,
)
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Any, TypeAlias, cast
from urllib.parse import urlencode

import attrs
import flask
from flask import Blueprint, Response, request
from jinja2 import Template

from audio_feeder import _object_types as ot
from audio_feeder import database_handler as dh
from audio_feeder import entry_filters as ef
from audio_feeder import media_renderer as mr
from audio_feeder import object_handler as oh
from audio_feeder import page_generator as pg
from audio_feeder import resources
from audio_feeder import rss_feeds as rf
from audio_feeder import text_normalization as tn
from audio_feeder.config import read_from_config
from audio_feeder.file_location import FileLocation
from audio_feeder.resolver import get_resolver

from . import __version__ as _VERSION
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
@functools.cache
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
    # Forms submit their empty fields as empty parameters, which have no
    # effect, so redirect to the same page without them for a tidier URL. The
    # theme and the colour scheme are stored in cookies, so they're also
    # dropped.
    params = list(request.args.items(multi=True))
    has_preferences = not _PREFERENCE_PARAMS.isdisjoint(request.args)
    if has_preferences or any(not value for _, value in params):
        kept = [
            (name, value)
            for name, value in params
            if value and name not in _PREFERENCE_PARAMS
        ]
        query = "?" + urlencode(kept) if kept else ""
        response = flask.redirect(request.path + query)
        if "theme" in request.args:
            _set_theme_cookie(response, request.args["theme"])
        if "scheme" in request.args:
            _set_scheme_cookie(response, request.args["scheme"])
        return response

    theme = request.cookies.get(THEME_COOKIE)
    themes = get_themes()
    if theme not in themes:
        theme = None
    # The default theme has both colour schemes
    theme_has_schemes = theme is None or themes[theme].has_schemes

    sort_args = get_sortable_args(request.args)
    try:
        entry_filter = ef.EntryFilter.from_args(request.args)
    except ef.InvalidFilter as e:
        logging.error("Ignoring invalid filter: %s", e)
        entry_filter = ef.EntryFilter()

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
        entry_cache["root"] = ef.library_root(entries)
    else:
        entries = entry_cache["base"]
    root = entry_cache["root"]

    books_table = cast(Mapping[ID, oh.Book], dh.get_database_table(TableName("books")))
    if "facets" not in entry_cache:
        entry_cache["facets"] = ef.facets(
            books_table[entry.data_id]
            for entry in entries
            if entry.data_id in books_table
        )
    facets = entry_cache["facets"]

    # The folder tree in the browse drawer counts the books matching the
    # other filters. It's used to choose both included and excluded folders,
    # so it ignores them both.
    tree_filter = entry_filter.without_folders()
    for cache_filter in (tree_filter, entry_filter):
        if cache_filter not in entry_cache:
            entry_cache[cache_filter] = cache_filter.apply(entries, books_table)
    tree_key = ("folder_tree", tree_filter)
    if tree_key not in entry_cache:
        entry_cache[tree_key] = ef.folder_tree(entry_cache[tree_filter])
    folder_tree = entry_cache[tree_key]
    entries = entry_cache[entry_filter]

    nav_generator = _book_nav_generator(len(entries), request.endpoint)

    # Retrieve or populate the specific sort cache. The sort order doesn't
    # depend on the page, so every page shares the same sorted list.
    arg_sort = (
        entry_filter,
        tuple(sorted((k, v) for k, v in sort_args.items() if k != "page")),
    )
    if arg_sort not in entry_cache:
        entries = get_sorted_entries(entries, sort_args)
        entry_cache[arg_sort] = entries
    else:
        entries = entry_cache[arg_sort]

    # Do the pagination
    entry_page = get_paged_entries(entries, sort_args)

    # The page jump menu labels each page with the range of its sort keys.
    labels_key = ("page_labels", arg_sort)
    if labels_key not in entry_cache:
        entry_cache[labels_key] = pg.page_range_labels(
            entries, sort_args["perPage"], _page_label_key(sort_args["orderBy"])
        )
    page_labels = entry_cache[labels_key]

    # Navigation links need to preserve the filter as well as the sort order
    filter_params = entry_filter.to_params()
    nav_args = {**filter_params, **sort_args}
    nav_list = nav_generator.get_pages(nav_args)
    # With no results, there are no pages, but the title still says "Page 0"
    max_page = max(len(nav_list) - 1, 0)
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

    sort_params = [
        ("orderBy", sort_args["orderBy"]),
        ("sortAscending", str(sort_args["sortAscending"])),
        ("perPage", str(sort_args["perPage"])),
    ]
    filter_param_pairs = _param_pairs(filter_params)

    page_data = {
        "entries": get_rendered_entries(entry_page),
        "nav_list": pg.windowed_nav(nav_list, page),
        # The number of each page, and the range of sort keys on it
        "page_options": [
            (nav_item.display, page_range)
            for nav_item, page_range in zip(nav_list, page_labels)
        ],
        "current_page": page,
        "page_jump_params": [*filter_param_pairs, *sort_params],
        "first_index": first_index,
        "final_index": final_index,
        "prev_index": prev_index,
        "next_index": next_index,
        "pagetitle": (
            f"Books: {ef.folder_label(entry_filter.folders[0], root)}: "
            f"Page {page} of {max_page}"
            if len(entry_filter.folders) == 1
            else f"Books: Page {page} of {max_page}"
        ),
        "site_images_url": site_images.url,
        "default_cover": os.path.join(site_images.url, "default_cover.svg"),
        "sort_options": get_sort_options(),
        "sort_args": sort_args,
        "entry_filter": entry_filter,
        # The browse drawer and the sort menu are separate forms, so each
        # passes on the other's settings as hidden fields.
        "filter_param_pairs": filter_param_pairs,
        "sort_params": sort_params,
        "filter_values": filter_params,
        "facets": facets,
        "folder_tree": folder_tree,
        "extra_folders": _extra_folders(
            folder_tree, entry_filter, entry_cache[tree_filter], root
        ),
        "open_folders": {
            parent
            for folder in (*entry_filter.folders, *entry_filter.not_folders)
            for parent in folder.parents
        },
        "tag_choices": _tag_choices(facets, entry_filter),
        "clear_filters_url": _books_url(ef.EntryFilter(), sort_args),
        "filter_count": entry_filter.criteria_count(),
        "breadcrumbs": _breadcrumbs(entry_filter, sort_args, root),
        "stylesheet_links": get_css_links(),
        "site_title": read_from_config("site_title"),
        "site_logo": _site_logo_url(),
        "themes": [(name, _theme_label(name)) for name in themes],
        "theme": theme,
        "theme_link": themes[theme].url if theme is not None else None,
        "theme_has_schemes": theme_has_schemes,
        "scheme": _get_scheme(),
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

    now = datetime.now(UTC)
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

    entry_obj = cast(oh.Entry, entry_table[ID(e_id)])
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


def _evaluate_bool_param(param: str) -> bool:
    return param.lower() == "true"


@root.route("/update")
def update():
    with UPDATE_LOCK:
        if not updater.UPDATE_IN_PROGRESS:
            reload_metadata: bool = request.args.get(
                "reloadMetadata", type=_evaluate_bool_param, default=False
            )
            check_hashes: bool = request.args.get(
                "checkHashes", type=_evaluate_bool_param, default=False
            )

            if reload_metadata or check_hashes:
                update_func = functools.partial(
                    updater.update,
                    reload_metadata=reload_metadata,
                    check_hashes=check_hashes,
                )
            else:
                update_func = updater.update

            updater.UPDATE_IN_PROGRESS = True
            background_thread = threading.Thread(target=update_func, daemon=True)
            background_thread.start()
        return flask.redirect(flask.url_for("root.update_status"))


@root.route("/version")
def version() -> str:
    return _VERSION


###
# Functions (probably want to move most of these to page_generator)
def _books_url(entry_filter: ef.EntryFilter, sort_args: Mapping[str, Any]) -> str:
    """The URL for the first page of books with a given filter and sort order."""
    link_args = {k: v for k, v in sort_args.items() if k != "page"}
    params = {**entry_filter.to_params(), **link_args}
    return flask.url_for("root.books") + "?" + urlencode(params, doseq=True)


def _param_pairs(
    params: Mapping[str, str | tuple[str, ...]],
) -> Sequence[tuple[str, str]]:
    """Query parameters as (name, value) pairs, with repeated names."""
    pairs = []
    for name, value in params.items():
        values = (value,) if isinstance(value, str) else value
        pairs.extend((name, v) for v in values)
    return pairs


def _extra_folders(
    folder_tree: Sequence[ef.FolderNode],
    entry_filter: ef.EntryFilter,
    entries: Sequence[oh.Entry],
    root: PurePosixPath | None,
) -> Sequence[ef.FolderNode]:
    """Included or excluded folders that aren't in the folder tree.

    The tree leaves out folders that are collapsed into their only subfolder,
    or that contain no books matching the other filters, but the browse
    drawer needs to show every selected folder so that it can be deselected
    (and so that it's kept when the form is submitted).
    """
    in_tree = set()
    to_visit = list(folder_tree)
    while to_visit:
        node = to_visit.pop()
        in_tree.add(node.folder)
        to_visit.extend(node.children)

    return [
        ef.FolderNode(
            folder=folder,
            label=ef.folder_label(folder, root),
            count=sum(1 for entry in entries if ef.in_folder(entry, folder)),
            children=(),
        )
        for folder in sorted({*entry_filter.folders, *entry_filter.not_folders})
        if folder not in in_tree
    ]


def _tag_choices(
    facets: ef.Facets, entry_filter: ef.EntryFilter
) -> Sequence[tuple[str, int]]:
    """The tags to offer in the browse drawer, with the number of books for each.

    Tags that are included or excluded come first, followed by the rest from
    most to least common.
    """
    selected = {*entry_filter.tags, *entry_filter.not_tags}
    counts = dict(facets.tags)
    return [
        *((tag, counts.get(tag, 0)) for tag in sorted(selected)),
        *((tag, count) for tag, count in facets.tags if tag not in selected),
    ]


def _breadcrumbs(
    entry_filter: ef.EntryFilter,
    sort_args: Mapping[str, Any],
    root: PurePosixPath | None,
) -> Sequence[Mapping[str, str | None]]:
    """Links to the folders above the included folder.

    These are only shown when exactly one folder is included, and they start
    below the library root, since every book is in the root.
    """
    if len(entry_filter.folders) != 1:
        return []

    # Changing folders keeps the other filters and sort settings, but goes
    # back to the first page.
    def folder_url(folder: PurePosixPath | None) -> str:
        folders = (folder,) if folder is not None else ()
        return _books_url(attrs.evolve(entry_filter, folders=folders), sort_args)

    (current,) = entry_filter.folders
    below_root = [
        folder
        for folder in ef.breadcrumbs(current)
        if root is None or root in folder.parents
    ]
    if not below_root:
        return []

    crumbs: list[Mapping[str, str | None]] = [{"name": "All", "url": folder_url(None)}]
    for folder in below_root:
        crumbs.append(
            {
                "name": folder.name,
                "url": folder_url(folder) if folder != current else None,
            }
        )
    return crumbs


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


def _page_label_key(order_by: str) -> Callable[[Any], pg.SortKey]:
    """The sort key that the page jump menu labels pages with."""
    if order_by == "author":
        return lambda el_e: next(
            (auth_obj.sort_name or auth_obj.name for auth_obj in el_e[2]), None
        )
    if order_by == "title":
        return lambda el_e: el_e[1].title
    return lambda el_e: getattr(el_e[0], order_by)


EntryObjects: TypeAlias = tuple[oh.Entry, oh.Book, Sequence[oh.Author]]


def get_sorted_entries(entry_list, sort_args):
    """
    Retrieve a list of entries, sorted according to the sort arguments.
    """
    return sort_entry_objects(
        get_entry_objects(entry_list),
        order_by=sort_args["orderBy"],
        ascending=sort_args["sortAscending"],
    )


def sort_entry_objects(
    entry_objects: Iterable[EntryObjects], order_by: str, ascending: bool = True
) -> Sequence[EntryObjects]:
    """Sort (entry, book, authors) triples by one of the sort options.

    Text fields (authors, series and titles) are sorted without regard to case
    or accents, and with numbers in numerical order; see
    :func:`text_normalization.sort_key`.
    """
    # Default sort order is author
    if order_by == "author":
        sort_order = ["author", "series", "title", "date_added", "last_modified"]
    elif order_by == "title":
        sort_order = ["title", "author", "series", "date_added", "last_modified"]
    elif order_by == "date_added":
        sort_order = ["date_added", "last_modified", "author", "series", "title"]
    elif order_by == "last_modified":
        sort_order = ["last_modified", "date_added", "author", "series", "title"]
    else:
        raise ValueError(f"Unknown sort option: {order_by!r}")

    def _sort_key(el_e: EntryObjects) -> tuple[Any, ...]:
        ent_obj, data_obj, auth_objs = el_e
        keys: dict[str, Any] = {}

        keys["author"] = tuple(
            tn.sort_key(auth_obj.sort_name or auth_obj.name or "")
            for auth_obj in auth_objs
        )

        keys["title"] = tn.sort_key(data_obj.title or "")
        # Despite the type annotations, in practice the series name and number
        # are a single string and integer.
        series_name = cast(str | None, data_obj.series_name)
        if series_name:
            keys["series"] = (tn.sort_key(series_name), data_obj.series_number or 0)
        else:
            keys["series"] = (tn.sort_key(""), 0)

        keys["date_added"] = ent_obj.date_added
        keys["last_modified"] = ent_obj.last_modified

        # Replace None with an empty string
        return tuple("" if keys[k] is None else keys[k] for k in sort_order)

    return sorted(entry_objects, key=_sort_key, reverse=not ascending)


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
@functools.cache
def get_sort_options() -> Mapping[str, str]:
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
            logging.error(
                "Number per page %s must be convertable to int.", per_page_arg
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


@functools.cache
def get_list_template() -> Template:
    # The page is sent on every request, so drop the indentation and newlines
    # around template tags, which would otherwise make up a lot of it.
    return _get_template(
        "pages_templates_loc",
        "list.tpl",
        resource_default="audio_feeder.data.templates.pages",
        trim_blocks=True,
        lstrip_blocks=True,
    )


@functools.cache
def get_feed_template() -> Template:
    return _get_template(
        "rss_templates_loc",
        "rss_feed.tpl",
        resource_default="audio_feeder.data.templates.rss",
    )


def _get_template(
    loc_entry: str,
    template_name: str,
    resource_default: str | None = None,
    **template_options: Any,
) -> Template:
    template_loc = read_from_config(loc_entry) / template_name

    if template_loc.exists():
        return Template(template_loc.read_text(), **template_options)
    elif resource_default is not None:
        return Template(
            resources.get_text_resource(resource_default, template_name),
            **template_options,
        )
    else:
        raise FileNotFoundError(f"Could not find template: {template_loc}")


@cache_utils.register_function_cache("misc")
@functools.cache
def get_renderer(rss_renderer: bool = False) -> pg.EntryRenderer:
    kwargs = {}
    if rss_renderer:
        kwargs["entry_templates_config"] = "rss_entry_templates_loc"
        kwargs["entry_templates_resource"] = (
            "audio_feeder.data.templates.rss.entry_types"
        )

    return pg.EntryRenderer(resolver=get_resolver(), **kwargs)


def _site_logo_url() -> str | None:
    """The URL of the logo in the top bar.

    This is ``None`` for audio-feeder's own logo, and the empty string for no
    logo.
    """
    logo: str | None = read_from_config("site_logo")
    if not logo or "://" in logo or logo.startswith("/"):
        return logo
    return get_resolver().resolve_static(logo).url


THEME_COOKIE = "theme"
SCHEME_COOKIE = "scheme"
_THEMES_DIR = "themes"
_PREFERENCE_PARAMS = frozenset({"theme", "scheme"})
# The theme and colour scheme are preferences for a browser, so they last a
# long time
_PREFERENCE_MAX_AGE = 10 * 365 * 24 * 60 * 60


class Scheme(enum.StrEnum):
    """A colour scheme chosen in place of the system's."""

    LIGHT = "light"
    DARK = "dark"


@attrs.frozen
class Theme:
    url: str
    # Whether the theme has both a light and a dark version, so that the
    # colour scheme can be chosen
    has_schemes: bool


def _set_theme_cookie(response: Response, theme: str) -> None:
    if theme in get_themes():
        response.set_cookie(
            THEME_COOKIE, theme, max_age=_PREFERENCE_MAX_AGE, samesite="Lax"
        )
    else:
        # Choosing the default theme (or one that doesn't exist) goes back to
        # the default
        response.delete_cookie(THEME_COOKIE, samesite="Lax")


def _set_scheme_cookie(response: Response, scheme: str) -> None:
    if scheme == "system":
        response.delete_cookie(SCHEME_COOKIE, samesite="Lax")
    elif scheme in tuple(Scheme):
        response.set_cookie(
            SCHEME_COOKIE, scheme, max_age=_PREFERENCE_MAX_AGE, samesite="Lax"
        )
    # Anything else leaves the colour scheme as it was


def _get_scheme() -> Scheme | None:
    """The colour scheme chosen in this browser, or None to follow the system."""
    try:
        return Scheme(request.cookies.get(SCHEME_COOKIE))
    except ValueError:
        return None


def _theme_label(name: str) -> str:
    return name.replace("_", " ").capitalize()


@cache_utils.register_function_cache("misc")
@functools.cache
def _install_default_css() -> None:
    """Copy the package's stylesheets into the static directory."""
    if read_from_config("disable_default_css"):
        return

    css_path = get_resolver().resolve_static(read_from_config("css_loc")).path
    assert css_path is not None
    resources.update_resource("audio_feeder.data.css", css_path)


@cache_utils.register_function_cache("misc")
@functools.cache
def get_themes() -> Mapping[str, Theme]:
    """The available themes, by name.

    Themes are the stylesheets in the ``themes`` directory of the CSS
    directory, which has the themes that come with audio-feeder, and to which
    more can be added. A theme is applied on top of the default stylesheets.
    A theme says that it has both a light and a dark version with
    ``color-scheme: light dark``.
    """
    _install_default_css()

    resolver = get_resolver()
    themes_loc = os.path.join(read_from_config("css_loc"), _THEMES_DIR)
    themes_path = resolver.resolve_static(themes_loc).path
    if themes_path is None or not themes_path.is_dir():
        return {}

    return {
        theme_path.stem: Theme(
            url=resolver.resolve_static(os.path.join(themes_loc, theme_path.name)).url,
            has_schemes=_has_both_schemes(theme_path.read_text(errors="replace")),
        )
        for theme_path in sorted(themes_path.glob("*.css"))
    }


_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_BOTH_SCHEMES = re.compile(r"color-scheme\s*:\s*(light\s+dark|dark\s+light)\b")


def _has_both_schemes(css: str) -> bool:
    return _BOTH_SCHEMES.search(_CSS_COMMENT.sub("", css)) is not None


@cache_utils.register_function_cache("misc")
@functools.cache
def get_css_links() -> Sequence[str]:
    resolver = get_resolver()
    css_loc = read_from_config("css_loc")
    css_locs: MutableSequence[str] = []
    if not read_from_config("disable_default_css"):
        _install_default_css()
        # Only the package's own stylesheets are used, since the directory can
        # have stylesheets left over from older versions.
        css_locs.extend(
            os.path.join(css_loc, child.name)
            for child in resources.get_children("audio_feeder.data.css")
            if child.is_file() and child.name.endswith(".css")
        )

    css_locs.extend(
        os.path.join(css_loc, css_file)
        for css_file in read_from_config("extra_css_files")
    )

    css_paths = [resolver.resolve_static(css_relpath).url for css_relpath in css_locs]

    return css_paths
