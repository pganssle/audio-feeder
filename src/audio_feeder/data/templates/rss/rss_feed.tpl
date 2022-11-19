<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0"
    xmlns:podcast="https://podcastindex.org/namespace/1.0"
    xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
    <channel>
        <title>{{ channel_title }}</title>
        <description>{{ channel_desc }}</description>
        <link>{{ channel_link }}</link>
        {% if not cover_image is sameas none %}
        <image>
            <title>{{ channel_title }}</title>
            <url>{{ cover_image }}</url>
            <link>{{ channel_link }}</link>
        </image>
        <itunes:image href="{{ cover_image }}" />
        {% endif %}
        <language>en-us</language>
        <lastBuildDate>{{ build_date }}</lastBuildDate>
        <pubDate>{{ pub_date }}</pubDate>
        <docs>http://blogs.law.harvard.edu/tech/rss</docs>
        <podcast:locked>yes</podcast:locked>
        <podcast:person>{{ author }}</podcast:person>

        <itunes:summary>{{ channel_desc }}</itunes:summary>
        <itunes:author>{{ author }}</itunes:author>
        <itunes:explicit>No</itunes:explicit>

        {% for item in items %}
        <item>
            <title>{{ channel_title }} {{ '%02d' % loop.index0 }}</title>
            <link>{{ channel_link }}</link>
            <description>{{ item.desc }}</description>
            <pubDate>{{ item.pubdate }}</pubDate>
            <guid>{{ item.guid }}</guid>
            <enclosure url="{{ item.url }}" length="{{ item.size }}" type="audio/mpeg"/>
            {% if not item.chapters_url is sameas none %}
                <podcast:chapters url="{{ item.chapters_url }}" type="application/json+chapters" />
            {% endif %}
        </item>
        {% endfor %}
    </channel>
</rss>
