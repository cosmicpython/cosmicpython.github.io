title:
layout: page
feature_image: "https://www.jpl.nasa.gov/spaceimages/images/largesize/PIA13111_hires.jpg"
feature_text: |
  # cosmic_python

  ___simple patterns for building complex applications___

---

_(Because "Cosmos" is the [opposite of Chaos](https://www.goodreads.com/quotes/604655-cosmos-is-a-greek-word-for-the-order-of-the), you see)_

<img src="images/cover.png" alt="Cover Image for Architecture Patterns with Python Book" style="float: right;" width="200" />


## The Book

* Read for free from the sources using Github previews:
  [github.com/cosmicpython/book](https://github.com/cosmicpython/book#table-of-contents) (CC-By-NC-ND)
* Read it online on O'Reilly Learning (aka Safari) 
  [learning.oreilly.com]( https://learning.oreilly.com/library/view/architecture-patterns-with/9781492052197/)
* Preorder print books on [Amazon.com](https://amzn.to/37pR2DH) or [Amazon.co.uk](https://amzn.to/38CmFu1)
* Buy a DRM-free ebook at [ebooks.com](https://www.ebooks.com/en-us/book/209971850/architecture-patterns-with-python/harry-percival/)

## Blog

### Recent posts

<ul>
  {% for post in site.posts reversed %}
    {% assign year = post.date | date: "%Y" %}
    {% if year != "2017" %}
      <li>
        <a href="{{ post.url }}">{{ post.date | date: "%Y-%m-%d" }} {{ post.title }}</a>
      </li>
    {% endif %}
  {% endfor %}
</ul>

### Classic 2017 Episodes on Ports & Adapters, by Bob

<ul>
  {% for post in site.posts reversed %}
    {% assign year = post.date | date: "%Y" %}
    {% if year == "2017" %}
      <li>
        <a href="{{ post.url }}">{{ post.date | date: "%Y-%m-%d" }} {{ post.title }}</a>
      </li>
    {% endif %}
  {% endfor %}
</ul>
