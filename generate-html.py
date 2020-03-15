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
    md_post_paths = glob.glob("blog/*.md")
    extensions = ['extra', 'smarty', 'meta', 'codehilite']
    _md = markdown.Markdown(extensions=extensions, output_format='html5')

    loader = jinja2.FileSystemLoader(searchpath="./")
    env = jinja2.Environment(loader=loader)

    all_posts = []
    for post in md_post_paths:
        print("rendering {0}".format(post))
        post_date =  date.fromisoformat(post[5:15])
        post_html_path = post.replace(".md", ".html").replace("blog/", "posts/")
        with open(post) as f:
            html = _md.convert(f.read())
            context = {
                'blog_publish_date': post_date,
                **_md.Meta
            }
            doc = env.get_template(TEMPLATE_FILE).render(content=html, baseurl=BASE_URL, url=post_html_path, **context)

        with open(post_html_path, "w") as f:
            f.write(doc)
        # all_posts.append(dict(**_md.Meta, date=post_date, rfc2822_date=format_datetime(post_date), link="{0}{1}".format(BASE_URL, url)))
        all_posts.append(dict(**_md.Meta, date=post_date, rfc2822_date='', link="{0}{1}".format(BASE_URL, post_html_path)))  # TODO fix date

    # index
    print("rendering index.html")
    with open('index.md') as f:
        index_html = _md.convert(f.read())
    doc = env.get_template('templates/index.html').render(
        content=index_html,
        posts=all_posts,
    )
    with open('index.html', "w") as f:
        f.write(doc)

    # Order blog posts by date published
    all_posts.sort(key=lambda item: item['date'], reverse=True)
    # Make the RSS feed
    with open("rss.xml", "w") as rss_f:
        rss_f.write(env.get_template(FEED_TEMPLATE_FILE).render(posts=all_posts, date=formatdate()))


if __name__ == "__main__":
    main()
