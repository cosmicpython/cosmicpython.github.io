---
title: Cosmic Python
layout: page
feature_image: "https://www.jpl.nasa.gov/spaceimages/images/largesize/PIA13111_hires.jpg"
feature_text: |
  ## Cosmic Python
---

{% include figure.html image="images/cover.png" alt="Cover Image for Architecture Patterns with Python Book" position="right" width="200" %}


## The Book

* Read for free from the sources using Github previews:
  [github.com/cosmicpython/book](https://github.com/cosmicpython/book#table-of-contents)
* Read in Early Release via O'Reilly Learning (aka Safari) 
  [learning.oreilly.com]( https://learning.oreilly.com/library/view/architecture-patterns-with/9781492052197/)
* Preorder on [Amazon.com](https://amzn.to/37pR2DH) or [Amazon.co.uk](https://amzn.to/38CmFu1)


## Blog Posts

<ul>
  {% for post in site.posts %}
    <li>
      <a href="{{ post.url }}">{{ post.date | date: "%Y-%m-%d" }} {{ post.title }}</a>
    </li>
  {% endfor %}
</ul>
