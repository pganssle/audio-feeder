{#- Details about the book shown on the book list, as an inline list -#}
<ul class="book_meta">
{%- if not series_name is sameas none %}<li class="series_data">{{ series_name }}{% if not series_number is sameas none %}, book {{ series_number }}{% endif %}</li>{% endif -%}
{%- if not duration is sameas none %}<li>{{ '%d h %02d min' % (duration // 3600, duration % 3600 // 60) }}</li>{% endif -%}
{%- if not pages is sameas none %}<li>{{ pages }} pages</li>{% endif -%}
{%- set published = original_pub_date if not original_pub_date is sameas none else pub_date -%}
{%- if not published is sameas none %}<li>Published {{ published }}</li>{% endif -%}
{%- if not isbn13 is sameas none or not isbn is sameas none %}<li>ISBN {{ isbn13 if not isbn13 is sameas none else isbn }}</li>{% endif -%}
{%- if not google_id is sameas none %}<li><a href="https://books.google.com/books?id={{ google_id }}">Google Books</a></li>{% endif -%}
{%- if not goodreads_id is sameas none %}<li><a href="https://www.goodreads.com/book/show/{{ goodreads_id }}">Goodreads</a></li>{% endif -%}
{%- if not ASIN is sameas none %}<li><a href="https://www.amazon.com/dp/{{ ASIN }}">Amazon</a></li>{% endif -%}
</ul>
