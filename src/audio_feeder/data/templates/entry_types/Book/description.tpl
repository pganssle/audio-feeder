{% if not series_name is sameas none %}<span class="series_data">{{ series_name }} {{ '%02d' % series_number }}</span><br/>{% endif %}
{% if not isbn13 is sameas none or not isbn is sameas none %}<span class="book_desc_field">ISBN</span>: <span class="book_desc_entry">{{ isbn13 if not isbn13 is sameas none else isbn }}</span><br/>{% endif %}
{% if not google_id is sameas none %}<span class="book_desc_field">Google Books</span>: <span class="book_desc_entry"><a href="https://books.google.com/books?id={{ google_id }}">{{ google_id }}</a></span><br/>{% endif %}
{% if not ASIN is sameas none %}<span class="book_desc_field">Amazon</span>: <a href="https://www.amazon.com/dp/{{asin}}">{{ASIN}}</a><br/>{% endif %}
{% if not goodreads_id is sameas none %}<span class="book_desc_field">Goodreads</span>: <span class="book_desc_entry"><a href="https://www.goodreads.com/book/show/{{goodreads_id}}">{{ goodreads_id }}</a></span><br/>{% endif %}
{% for field_name, entry_field in [("Publication Date", pub_date), ("Original Publication Date", original_pub_date), ("Duration", duration), ("Pages", pages)] %}
{% if not entry_field is sameas none %}
    <span class="book_desc_field">{{ field_name }}</span>: <span class="book_desc_entry">{{ entry_field }}</span><br/>
{% endif %}
{% endfor %}
{{ description }}

