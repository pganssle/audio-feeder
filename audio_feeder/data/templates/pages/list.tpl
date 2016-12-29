<!DOCTYPE html>
<html lang="en">
<head>
    <title>{% block title %}{{ pagetitle }}{% endblock %}</title>
    <meta name="description" content="List of content served">

    {% if not stylesheet_links is sameas none %}
    {% for stylesheet_link in stylesheet_links %}
    <link rel="stylesheet" href="{{stylesheet_link}}">
    {% endfor %}
    {% endif %}

    {% if not favicon is sameas none %}
    <link rel="icon" type="{{favicon.type}}" href="{{favicon.url}}">
    {% endif %}

</head>
<body>
<script>
/* Initialize all expanders */
function init_elements() {
    hidden_descs = document.querySelectorAll("span.hidden_description_section");
    for (var i = 0; i < hidden_descs.length; i++) {
        el = hidden_descs[i];
        el.style.display = "none";
    }
}

window.onload = init_elements;

function toggle_hidden(entry_id) {
    target = document.querySelector("a.read_more_link#e" + entry_id);
    selection_query = "span.hidden_description_section#e" + entry_id;
    desc_section = document.querySelector(selection_query);
    ellipsis = document.querySelector('span.expander_ellipsis#e' + entry_id);

    if (desc_section.style.display == "none") {
        // Currently hidden, toggling to visible
        desc_section.style.display = "inline";
        ellipsis.style.display = "none";
        target.innerHTML = "(Collapse)";
    } else {
        desc_section.style.display = "none";
        target.innerHTML = "(Read More)";
        ellipsis.style.display = "inline";
    }
}
</script>

{% block topnav %}{% endblock %}
    <table class='maintable'>
    {% block navbar %}
        <tr>
            <td colspan=3><center>
                <table class="navtable" width="100%">
                    <tr>
                        <td class="nav_arrow"><a{% if not first_index is sameas none %} href="{{ first_index }}"{% endif %}><img class="nav_arrow" id="firstnav" src="{{ site_images_url }}/double_left_arrow.svg" align="left"></a></td>
                        <td class="nav_arrow"><a{% if not prev_index is sameas none %} href="{{prev_index}}"{% endif %}><img class="nav_arrow" id="backnav" src="{{ site_images_url }}/left_arrow.svg" align="left"></a></td>
                        <td class="nav_links">
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
                        <td class="nav_arrow"><a {% if not next_index is sameas none %} href="{{next_index}}"{% endif%}><img class="nav_arrow" id="fwdnav" src="{{ site_images_url }}/right_arrow.svg" align="right"></a></td>
                        <td class="nav_arrow"><a {% if not final_index is sameas none %} href="{{ final_index }}" {% endif %}><img class="nav_arrow" id="lastnav" src="{{ site_images_url }}/double_right_arrow.svg" align="right"></a></td>
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
                <img src="{{ entry.cover_url if not entry.cover_url is sameas none else default_cover }}" class="cover_img" />
            </td>
            <td class="qr_col" id="{{ entry.id }}">
                <img src="{{ entry.qr_img_url }}" class="qr_img" />
            </td>
            <td class="entry_body" id="{{ entry.id }}">
                <h3 class="entry_title"><a class="entry_link" href="{{ entry.rss_url }}">{{ entry.name }}</a></h3>
                {% if entry.truncation_point <= 0 %}{{ entry.description }}{% else %}
                {{ entry.description[0:entry.truncation_point] }}{% if entry.description|length > entry.truncation_point %}<span class="hidden_description_section" id="e{{ entry.id }}">{{ entry.description[entry.truncation_point:] }}</span><span class="hidden_expander_span" id="e{{ entry.id }}"><span class="expander_ellipsis" id="e{{entry.id}}">... </span><a href="javascript:void(0);" class='read_more_link' id="e{{ entry.id }}" onclick="toggle_hidden({{ entry.id }})">(Read More)</a></span>{%endif%}
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