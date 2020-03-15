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

from dataclasses import dataclass

@dataclass
class Post:
    title: str
    author: str
    md_path: str
    date: date

    @property
    def html_path(self):
        return self.md_path.replace('blog/', 'posts/').replace('.md', '.html')




def main():
    md_post_paths = sorted(glob.glob("blog/*.md"))
    extensions = ['extra', 'smarty', 'meta', 'codehilite']
    _md = markdown.Markdown(extensions=extensions, output_format='html5')

    loader = jinja2.FileSystemLoader(searchpath="./")
    env = jinja2.Environment(loader=loader)

    all_posts = []
    for md_post_path in md_post_paths:
        print("rendering", md_post_path)
        post_date = date.fromisoformat(md_post_path[5:15])
        with open(md_post_path) as f:
            html = _md.convert(f.read())
        post = Post(
            md_path=md_post_path, date=post_date,
            author=_md.Meta['author'][0],
            title=_md.Meta['title'][0],
        )
        doc = env.get_template(TEMPLATE_FILE).render(
            content=html, baseurl=BASE_URL, url=post.html_path, post=post,
        )

        with open(post.html_path, "w") as f:
            f.write(doc)
        # all_posts.append(dict(**_md.Meta, date=post_date, rfc2822_date=format_datetime(post_date), link="{0}{1}".format(BASE_URL, url)))
        all_posts.append(post)  # TODO fix date

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
    all_posts.sort(key=lambda p: p.date, reverse=True)
    # Make the RSS feed
    with open("rss.xml", "w") as rss_f:
        rss_f.write(env.get_template(FEED_TEMPLATE_FILE).render(posts=all_posts, date=formatdate()))


if __name__ == "__main__":
    main()
