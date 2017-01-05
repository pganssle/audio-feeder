#! /usr/bin/env python3

import html
import itertools as it
import logging
import os

from datetime import datetime, timezone

from flask import Blueprint, request
import flask

from jinja2 import Template

from audio_feeder import page_generator as pg
from audio_feeder import database_handler as dh
from audio_feeder import rss_feeds as rf
from audio_feeder.resolver import get_resolver
from audio_feeder.config import read_from_config, init_config

root = Blueprint('root', __name__)

###
# Pages

@root.route('/')
def main_index():
    """
    The base index - for now this redirects to the audiobooks.
    """
    return flask.redirect(flask.url_for('root.books'))

@root.route('/books')
def books():
    """
    The main page for listing audiobooks
    """
    sort_args = get_sortable_args(request.args)

    # Retrieve or populate the entry cache.
    entry_cache = getattr(books, '_cache', None)
    if entry_cache is None:
        entry_cache = {}
        books._cache = entry_cache

    if 'base' not in entry_cache:
        # Get the list of entries (SELECT * from entries WHERE type == 'book')
        entries = [entry_obj
                   for entry_obj in dh.get_database_table('entries').values()
                   if entry_obj.type == 'Book']

        entry_cache['base'] = entries
    else:
        entries = entry_cache['base']

    nav_generator = getattr(books, '_generator', None)
    if nav_generator is None:
        nav_generator = pg.NavGenerator(len(entries),
                                        flask.url_for(request.endpoint))

        books._generator = nav_generator

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
    page = sort_args['page']
    first_index = nav_list[0].url or request.path
    prev_index = nav_list[max((page - 1, 0))]
    next_index = nav_list[min((page + 1, len(nav_list) - 1))]

    resolver = get_resolver()
    site_images = resolver.resolve_static(read_from_config('site_images_loc'))

    page_data = {
        'entries': get_rendered_entries(entry_page),
        'nav_list': nav_generator.get_pages(sort_args),
        'first_index': nav_list[0].url,
        'final_index': nav_list[-1].url,
        'prev_index': prev_index.url,
        'next_index': next_index.url,
        'pagetitle': 'Books: Page {} of {}'.format(page, len(nav_list)),
        'site_images_url': site_images.url,
        'default_cover': os.path.join(site_images.url, 'default_cover.svg'),
        'stylesheet_links': get_css_links(),
        'favicon': None,
    }

    # Apply the template
    t = get_list_template()
    return t.render(page_data)


@root.route('/rss/<int:e_id>.xml')
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

    entry_table = dh.get_database_table('entries')
    if e_id not in entry_table:
        flask.abort(404)

    entry_obj = entry_table[e_id]
    data_obj = dh.get_data_obj(entry_obj)

    # Render the main "feed-wide" portions of this
    renderer = get_renderer(rss_renderer=True)
    rendered_page = renderer.render(entry_obj, data_obj)

    channel_title = rendered_page['name']
    channel_desc = rendered_page['description']

    build_date = entry_obj.last_modified
    pub_date = entry_obj.date_added

    author = rendered_page['author']
    
    cover_image = entry_obj.cover_images[0] if entry_obj.cover_images else None
    if cover_image is not None:
        cover_image = get_resolver().resolve_static(cover_image).url

    # This gives me the "items" list
    feed_items = rf.load_feed_items(entry_obj)

    payload = {
        'channel_title': channel_title,
        'channel_desc': channel_desc,
        'channel_link': request.path,
        'build_date': build_date,
        'pub_date': pub_date,
        'author': author,
        'cover_image': cover_image,
        'items': feed_items
    }

    payload = {k: rf.wrap_field(v) for k, v in payload.items()}

    t = get_feed_template()

    return t.render(payload)


###
# Functions (probably want to move most of these to page_generator)
def get_rendered_entries(entry_list):
    renderer = get_renderer()

    o = [renderer.render(entry_obj, data_obj)
            for entry_obj, data_obj, auth_objs in entry_list]

    return o

def get_paged_entries(entry_list, sort_args):
    per_page = sort_args['perPage']
    page = sort_args['page']
    start_loc = page * per_page
    end_loc = start_loc + per_page

    return entry_list[start_loc:end_loc]


def get_sorted_entries(entry_list, sort_args):
    """
    Retrieve a list of entries, sorted according to the sort arguments.
    """
    order_by = sort_args['orderBy']
    sort_ascending = sort_args['sortAscending']

    # Default sort order is author
    if order_by == 'author':
        sort_order = ['author', 'series', 'title', 'date_added', 'last_modified']
    elif order_by == 'title':
        sort_order = ['title', 'author', 'series', 'date_added', 'last_modified']
    elif order_by == 'date_added':
        sort_order = ['date_added', 'last_modified', 'author', 'series', 'title']
    elif order_by == 'last_modified':
        sort_order = ['last_modified', 'date_added', 'author', 'series', 'title']

    def _sort_key(el_e):
        ent_obj, data_obj, auth_objs = el_e
        keys = {}

        keys['author'] = [auth_obj.sort_name or auth_obj.name
                          for auth_obj in auth_objs]

        keys['title'] = data_obj.title
        if data_obj.series_name:
            keys['series'] = (data_obj.series_name, data_obj.series_number)
        else:
            keys['series'] = ('', 0)

        keys['date_added'] = ent_obj.date_added
        keys['last_modified'] = ent_obj.last_modified

        # Replace None with an empty string
        return tuple(keys[k] or '' for k in sort_order)

    return sorted(get_entry_objects(entry_list), key=_sort_key,
                  reverse=not sort_ascending)


def get_entry_objects(entry_list):
    """
    Retrieve a list of (entry, data_obj) pairs.
    """
    # Grouping these together like this just to minimize the number of calls
    # to get_database_table.
    author_table = dh.get_database_table('authors')

    for table_name, group in it.groupby(entry_list, key=lambda x: x.table):
        table = dh.get_database_table(table_name)

        for entry_obj in group:
            data_obj = table[entry_obj.data_id]

            # Retrieve the author objects as well
            author_objs = [author_table[author_id] for author_id in data_obj.author_ids]

            yield (entry_obj, data_obj, author_objs)


def get_sortable_args(args):
    # Ascending / descending
    sort_order = args.get('sortAscending', 'True').lower()
    sort_ascending = sort_order != 'false'

    # Sort field
    sort_options = ('author', 'title', 'date_added', 'last_modified')
    order_by = args.get('orderBy', None)

    if order_by is not None and order_by not in sort_options:
        logging.error('Order by option {} invalid, '.format(order_by) +
                      'must be one of: {}'.format(','.join(sort_options)))
        order_by = None

    if order_by is None:
        order_by = sort_options[0]

    # Items per page
    per_page_dflt = 25
    per_page = None
    if 'perPage' in args:
        try:
            per_page_arg = args.get('perPage')
            per_page = int(per_page_arg)
        except ValueError:
            logging.error('Number per page {} '.format(perPage) +
                          'must be convertable to int.')

    per_page = per_page or per_page_dflt

    # Current page location
    page = int(args.get('page', 0))

    args = {
        'sortAscending': sort_ascending,
        'orderBy': order_by,
        'perPage': per_page,
        'page': page
    }

    return args


def get_list_template():
    template = getattr(get_list_template, '_template', None)
    if template is None:
        template = _get_template('pages_templates_loc', 'list.tpl')
        get_list_template._template = template

    return template


def get_feed_template():
    template = getattr(get_feed_template, '_template', None)
    if template is None:
        template = _get_template('rss_templates_loc', 'rss_feed.tpl')
        get_feed_template._template = template

    return get_feed_template._template


def _get_template(loc_entry, template_name):
    template_loc = read_from_config(loc_entry)
    template_loc = os.path.join(template_loc, template_name)

    with open(template_loc, 'r') as f:
        template = Template(f.read())

    return template


def get_renderer(rss_renderer=False):
    renderer = getattr(get_renderer, '_renderer', {})
    if rss_renderer not in renderer:
        resolver = get_resolver()

        kwargs = {}
        if rss_renderer:
            kwargs['entry_templates_config'] = 'rss_entry_templates_loc'

        renderer[rss_renderer] = pg.EntryRenderer(resolver=resolver, **kwargs)

        get_renderer._renderer = renderer

    return renderer[rss_renderer]


def get_css_links():
    resolver = get_resolver()
    css_loc = read_from_config('css_loc')
    css_locs = [os.path.join(css_loc, css_file)
                for css_file in read_from_config('main_css_files')]

    css_paths = [resolver.resolve_static(css_relpath).url
        for css_relpath in css_locs]

    return css_paths
