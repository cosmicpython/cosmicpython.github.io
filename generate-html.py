#!/usr/bin/env python
# copied from https://github.com/tonybaloney/tonybaloney.github.io/blob/master/blog-gen.py
import markdown
import jinja2
import glob
from datetime import date, datetime
from email.utils import formatdate, format_datetime  # for RFC2822 formatting

TEMPLATE_FILE = "templates/blog_post_template.html"
FEED_TEMPLATE_FILE = "templates/rss_feed_template.xml"
BASE_URL = "https://tonybaloney.github.io/"

def main():
    posts = glob.glob("blog/*.md")
    extensions = ['extra', 'smarty', 'meta']
    _md = markdown.Markdown(extensions=extensions, output_format='html5')

    loader = jinja2.FileSystemLoader(searchpath="./")
    env = jinja2.Environment(loader=loader)

    all_posts = []
    for post in posts:
        print("rendering {0}".format(post))
        post_date =  date.fromisoformat(post[5:15])
        url = post.replace(".md", ".html").replace("blog/", "posts/")
        with open(post) as post_f:
            html = _md.convert(post_f.read())
            context = {
                'blog_publish_date': post_date,
                **_md.Meta
            }
            doc = env.get_template(TEMPLATE_FILE).render(content=html, baseurl=BASE_URL, url=url, **context)

        post_html = url
        with open(post_html, "w") as post_html_f:
            post_html_f.write(doc)
        # all_posts.append(dict(**_md.Meta, date=post_date, rfc2822_date=format_datetime(post_date), link="{0}{1}".format(BASE_URL, url)))
        all_posts.append(dict(**_md.Meta, date=post_date, rfc2822_date='', link="{0}{1}".format(BASE_URL, url)))

    # Order blog posts by date published
    all_posts.sort(key=lambda item: item['date'], reverse=True)
    # Make the RSS feed
    with open("rss.xml", "w") as rss_f:
        rss_f.write(env.get_template(FEED_TEMPLATE_FILE).render(posts=all_posts, date=formatdate()))


if __name__ == "__main__":
    main()
