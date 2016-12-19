<!DOCTYPE html>
<html lang="en">
<head>
    <title>{% block title %}{{ pagetitle }}{% endblock %}</title>
</head>
<body>
{% block topnav %}{% endblock %}
    <table>
    {% block navbar %}
        <tr>
            <td colspan=3><center>
                <table width="100%">
                    <tr>
                        <td><a href="index.html"><img class="nav_arrow", id="firstnav" src="audiobook_images/double_left_arrow.png" align="left"></a></td>
                        <td><a href="{{prev_index}}"><img class="nav_arrow" id="backnav" src="audiobook_images/left_arrow.png" align="left"></a></td>
                        <td>
                            {% block navlist %}
                            {% for nav_item in nav_list %}
                                {% if not nav_item.url is sameas none %}
                                    <a class="nav_link" href="{{ nav_item.url }}">{{ nav_item.display }}</a>
                                {% else %}
                                    {{ nav_item.display }}
                                {% endif %}
                            {% endfor %}
                            {% endblock %}
                        </td>
                        <td><a href="{{next_index}}"><img class="nav_arrow" id="fwdnav" src="audiobook_images/right_arrow.png" align="right"></a></td>
                        <td><a href="{{final_index}}"><img class="nav_arrow" id="lastnav" src="audiobook_images/double_right_arrow.jpg" align="right"></a></td>
                    </tr>
                </table>
                </center>
            </td>
        </tr>
    {% endblock %}
    {% block audiobooks %}
    {% for book in books %}
        <tr class="book_row {{ loop.cycle('odd', 'even') }}" id="{{ book.id }}">
            <td class="cover_col" id="{{ book.id }}">
                <img src="{% book.cover_url if not book.cover_url is sameas none else default_cover %}" class="cover_img" />
            </td>
            <td class="qr_col" id="{{ book.id }}">
                <img src="{{ book.qr_img_url }}" class="qr_img" />
            </td>
            <td class="book_body" id="{{ book.id }}">
                <h3 class="book_title"><a class="book_link" src="{{ book.rss_url }}">{{ book.name }}</a></h3><br/>
                {{ book.description[0:book.truncation_point] }}{% if not book.truncation_point is sameas none and book.description|length > book.truncation_point %}<span class="hidden_description_section">{{ book.description[book.trunction_point:] }}</span><span class="hidden_expander_span" id="{{ book.id }}">(Read More)</span>
                {% endif %}
            </td>
        </tr>
    {% endfor %}
    {% endblock %}
    {{ self.navbar() }}
    </table>
{% block botnav %}{% endblock %}
</body>
</html>