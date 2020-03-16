#!/usr/bin/env python
from dataclasses import dataclass
from pathlib import Path
import json
from lxml import html
import subprocess

DEST = Path('_site/book')

CHAPTERS = [
    c.replace('.asciidoc', '.html')
    for c in json.loads(Path('book/atlas.json').read_text())['files']
    if c.partition('.')[0] not in [
        'cover',
        'titlepage',
        'copyright',
        'toc',
        'ix',
        'author_bio',
        'colo',
    ]
]




def parse_chapters():
    for chapter in CHAPTERS:
        path = Path('book') / chapter
        yield chapter, html.fromstring(path.read_text())


def get_anchor_targets(parsed_html):
    ignores = {'header', 'content', 'footnotes', 'footer', 'footer-text'}
    all_ids = [
        a.get('id') for a in parsed_html.cssselect('*[id]')
    ]
    return [i for i in all_ids if not i.startswith('_') and i not in ignores]

@dataclass
class ChapterInfo:
    href_id: str
    chapter_title: str
    subheaders: list
    xrefs: list


def get_chapter_info():
    chapter_info = {}
    appendix_numbers = list('ABCDEFGHIJKL')
    chapter_numbers = list(range(1, 100))
    part_numbers = list(range(1, 10))

    for chapter, parsed_html in parse_chapters():
        print('getting info from', chapter)

        if not parsed_html.cssselect('h2'):
            header = parsed_html.cssselect('h1')[0]
        else:
            header = parsed_html.cssselect('h2')[0]
        href_id = header.get('id')
        if href_id is None:
            href_id = parsed_html.cssselect('body')[0].get('id')
        subheaders = [h.get('id') for h in parsed_html.cssselect('h3')]

        chapter_title = header.text_content()
        chapter_title = chapter_title.replace('Appendix A: ', '')

        if chapter.startswith('chapter_'):
            chapter_no = chapter_numbers.pop(0)
            chapter_title = f'Chapter {chapter_no}: {chapter_title}'

        if chapter.startswith('appendix_'):
            appendix_no = appendix_numbers.pop(0)
            chapter_title = f'Appendix {appendix_no}: {chapter_title}'

        if chapter.startswith('part'):
            part_no = part_numbers.pop(0)
            chapter_title = f'Part {part_no}: {chapter_title}'

        if chapter.startswith('epilogue'):
            chapter_title = f'Epilogue: {chapter_title}'

        xrefs = get_anchor_targets(parsed_html)
        chapter_info[chapter] = ChapterInfo(href_id, chapter_title, subheaders, xrefs)

    return chapter_info


def fix_xrefs(contents, chapter, chapter_info):
    parsed = html.fromstring(contents)
    links = parsed.cssselect('a[href^=\#]')
    for link in links:
        for other_chap in CHAPTERS:
            if other_chap == chapter:
                continue
            chapter_id = chapter_info[other_chap].href_id
            href = link.get('href')
            targets = ['#' + x for x in chapter_info[other_chap].xrefs]
            if href == '#' + chapter_id:
                link.set('href', f'/book/{other_chap}')
            elif href in targets:
                link.set('href', f'/book/{other_chap}{href}')

    return html.tostring(parsed)


def fix_title(contents, chapter, chapter_info):
    parsed = html.fromstring(contents)
    titles = parsed.cssselect('h2')
    if titles and titles[0].text.startswith('Appendix A'):
        title = titles[0]
        title.text = chapter_info[chapter].chapter_title
    return html.tostring(parsed)

def copy_chapters_across_with_fixes(chapter_info, fixed_toc):
    # comments_html = open('disqus_comments.html').read()
    # buy_book_div = html.fromstring(open('buy_the_book_banner.html').read())
    # analytics_div = html.fromstring(open('analytics.html').read())
    # load_toc_script = open('load_toc.js').read()

    for chapter in CHAPTERS:
        old_contents = Path(f'book/{chapter}').read_text()
        new_contents = fix_xrefs(old_contents, chapter, chapter_info)
        new_contents = fix_title(new_contents, chapter, chapter_info)
        parsed = html.fromstring(new_contents)
        body = parsed.cssselect('body')[0]
        if header := parsed.cssselect('#header'):
            # head = parsed.cssselect('head')[0]
            # head.append(html.fragment_fromstring('<script>' + load_toc_script + '</script>'))
            body.set('class', 'article toc2 toc-left')
            header[0].append(fixed_toc)
        # body.insert(0, buy_book_div)
        # body.append(html.fromstring(
        #     comments_html.replace('CHAPTER_NAME', chapter.split('.')[0])
        # ))
        # body.append(analytics_div)
        fixed_contents = html.tostring(parsed)
        target = DEST / chapter
        print('writing', target)
        target.write_bytes(fixed_contents)



def extract_toc_from_book():
    parsed = html.fromstring(Path('book/book.html').read_text())
    return parsed.cssselect('#toc')[0]



def fix_toc(toc, chapter_info):
    href_mappings = {}
    for chapter in CHAPTERS:
        chap = chapter_info[chapter]
        if chap.href_id:
            href_mappings['#' + chap.href_id] = f'/book/{chapter}'
        for subheader in chap.subheaders:
            href_mappings['#' + subheader] = f'/book/{chapter}#{subheader}'

    def fix_link(href):
        if href in href_mappings:
            return href_mappings[href]
        return href

    toc.rewrite_links(fix_link)
    toc.set('class', 'toc2')
    return toc


def main():
    toc = extract_toc_from_book()
    chapter_info = get_chapter_info()
    fixed_toc = fix_toc(toc, chapter_info)
    copy_chapters_across_with_fixes(chapter_info, fixed_toc)
    rsync_images()


if __name__ == '__main__':
    main()
