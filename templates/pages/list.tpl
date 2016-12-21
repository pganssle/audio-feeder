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
                        <td><a href="index.html"><img class="nav_arrow", id="firstnav" src="{{ site_images_url }}/double_left_arrow.png" align="left"></a></td>
                        <td><a href="{{prev_index}}"><img class="nav_arrow" id="backnav" src="{{ site_images_url }}/left_arrow.png" align="left"></a></td>
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
                        <td><a href="{{next_index}}"><img class="nav_arrow" id="fwdnav" src="{{ site_images_url }}/right_arrow.png" align="right"></a></td>
                        <td><a href="{{final_index}}"><img class="nav_arrow" id="lastnav" src="{{ site_images_url }}/double_right_arrow.jpg" align="right"></a></td>
                    </tr>
                </table>
                </center>
            </td>
        </tr>
    {% endblock %}
    {% block mainlist %}
    {% for entry in entries %}
        <tr class="entry_row {{ loop.cycle('odd', 'even') }}" id="{{ entry.id }}">
            <td class="cover_col" id="{{ entry.id }}">
                <img src="{% entry.cover_url if not entry.cover_url is sameas none else default_cover %}" class="cover_img" />
            </td>
            <td class="qr_col" id="{{ entry.id }}">
                <img src="{{ entry.qr_img_url }}" class="qr_img" />
            </td>
            <td class="entry_body" id="{{ entry.id }}">
                <h3 class="entry_title"><a class="entry_link" src="{{ entry.rss_url }}">{{ entry.name }}</a></h3><br/>
                {{ entry.description[0:entry.truncation_point] }}{% if not entry.truncation_point is sameas none and entry.description|length > entry.truncation_point %}<span class="hidden_description_section">{{ entry.description[entry.trunction_point:] }}</span><span class="hidden_expander_span" id="{{ entry.id }}">(Read More)</span>
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