#! /usr/bin/env python3
DESCRIPTION = """This is the main script that runs the audio_feeder backend.
"""
import itertools as it
import logging
import os

from flask import Flask, request
import flask

from jinja2 import Template

from audio_feeder import page_generator as pg
from audio_feeder import database_handler as dh
from audio_feeder.config import read_from_config, init_config

app = Flask('audio_feeder')

###
# Pages

@app.route('/')
def main_index():
    """
    The base index - for now this redirects to the audiobooks.
    """
    return flask.redirect(flask.url_for('books'))


@app.route('/books')
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
    prev_index = nav_list[min((page - 1, 0))]
    next_index = nav_list[min((page + 1, len(nav_list) - 1))]

    page_data = {
        'entries': get_rendered_entries(entry_page),
        'nav_list': nav_generator.get_pages(sort_args),
        'first_index': nav_list[0].url,
        'final_index': nav_list[-1].url,
        'prev_index': prev_index,
        'next_index': next_index,
        'pagetitle': 'Books: Page {} of {}'.format(page, len(nav_list)),
        'site_images_url': read_from_config('site_images_path'),
        'default_cover': 'default.png',   # Placeholder.
    }

    # Apply the template
    t = get_list_template()
    return t.render(page_data)


###
# Functions (probably want to move most of these to page_generator)
def get_rendered_entries(entry_list):
    renderer = get_renderer()

    return [renderer.render(entry_obj, data_obj)
            for entry_obj, data_obj in entry_list]

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

    # Sort by author and title
    return list(get_entry_objects(entry_list))


def get_entry_objects(entry_list):
    """
    Retrieve a list of (entry, data_obj) pairs.
    """
    # Grouping these together like this just to minimize the number of calls
    # to get_database_table.
    for table_name, group in it.groupby(entry_list, key=lambda x: x.table):
        table = dh.get_database_table(table_name)

        for entry_obj in group:
            data_obj = table[entry_obj.data_id]

            yield (entry_obj, data_obj)


def get_sortable_args(args):
    # Ascending / descending
    sort_order = args.get('sortOrder', 'ascending').lower()
    if sort_order not in ('ascending', 'descending'):
        logging.error('Sort order {} invalid, must '.format(sort_order) +
                      'be "ascending" or "descending"')

    sort_ascending = sort_order == 'ascending'

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
        template_loc = read_from_config('pages_templates_loc')
        template_loc = os.path.join(template_loc, 'list.tpl')

        with open(template_loc, 'r') as f:
            template = Template(f.read())

        get_list_template._template = template

    return template


def get_renderer():
    renderer = getattr(get_renderer, '_renderer', None)
    if renderer is None:
        resolver = pg.UrlResolver(
            base_path=read_from_config('static_media_path'),
            base_url=read_from_config('base_url')
        )

        renderer = pg.EntryRenderer(url_resolver=resolver)

        get_renderer._renderer = renderer

    return renderer


def _author_sort_helper(authors):
    """
    Temporary measure - turn author list into sort-by-last-name for now,
    until we implement storing this in the actual database.
    """
    def sort_name(author):
        # Most basic heuristic.
        first, sep, last = author.rpartition(' ')
        if first:
            return ','.join((last, first))
        else:
            return last

    return tuple(sort_name(author) for author in authors)

###
# Scripts
def run():
    import argparse

    parser = argparse.ArgumentParser(description=DESCRIPTION)

    parser.add_argument('-hn', '--host', type=str, default='localhost',
        help='The host to run the application on.')

    parser.add_argument('-p', '--port', type=int, default=9090,
        help='The port to run the application on.')

    args = parser.parse_args()

    init_config(base_host=args.host, base_port=args.port)

    app.static_folder = read_from_config('static_media_path')

    app.run(host=args.host, port=args.port)

    print(read_from_config('qr_cache_path'))