<?xml version="1.0" encoding="UTF-8"?>
<rss xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" version="2.0">
 
    <channel>

        <title>{{ channel_title }}</title>
        <description>{{ channel_desc }}</description>
        <link>{{ channel_link }}</link>
        {{ cover_image_tag }}
        <language>en-us</language>
        <lastBuildDate>{{ build_date }}</lastBuildDate>
        <pubDate>{{ pub_date }}</pubDate>
        <docs>http://blogs.law.harvard.edu/tech/rss</docs>
        
        <itunes:author>{{ author }}</itunes:author>
        <itunes:summary>{{ channel_desc }}</itunes:summary>

        <itunes:explicit>No</itunes:explicit>

        {{ itunes_cover_image_tag }}
        
        {% for item in items %}
        <item>
            <title>{item.title}</title>
            <link>{channel_link}</link>
            <description>{item.desc}</description>
            <pubDate>{item.pubdate}</pubDate>
            <guid>{item.guid}</guid>
            <enclosure url="{item.url}" length="{item.size}" type="audio/mpeg"/>
        </item>
        {% endfor %}

    </channel>

</rss>