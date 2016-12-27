{% if not isbn13 is sameas none or not isbn is sameas none %}<b>ISBN</b>: {{ isbn13 if not isbn13 is sameas none else isbn }}<br/>{% endif %}{% if not google_id is sameas none %}<b>Google Books</b>: <a href="https://books.google.com/books?id={{ google_id }}">{{ google_id }}</a><br/>{% endif %}{% if not ASIN is sameas none %}<b>Amazon</b>: <a href="https://www.amazon.com/dp/{{asin}}">{{ASIN}}</a><br/>{% endif %}{% if not goodreads_id is sameas none %}<b>Goodreads</b>: a href="https://www.goodreads.com/book/show/{{goodreads_id}}">{{ goodreads_id }}</a><br/>{% endif %}
{% for field_name, entry_field in [("Publication Date", pub_date), ("Original Publication Date", original_pub_date), ("Duration", duration), ("Pages", pages)] %}
{% if not entry_field is sameas none %}
    <b>{{ field_name }}</b>: {{ entry_field }}<br/>
{% endif %}
{% endfor %}
{{ description }}

