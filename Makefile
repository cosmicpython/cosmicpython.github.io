serve:
	python -m http.server --directory=_site 8888

build:
	./generate-html

watch-build:
	ls **/*.md **/*.html *.py | entr ./generate-html.py

update-book:
	cd book && make html
	./copy-and-fix-book-html.py
	rsync -a -v book/images/ _site/book/images/


