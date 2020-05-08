all: build update-book serve

build:
	./generate-html.py

serve:
	python -m http.server

watch-build:
	ls **/*.md **/*.html *.py | entr ./generate-html.py

update-book:  ## assumes book repo is at ../book
	cd ../book && make html
	./copy-and-fix-book-html.py
	rsync -a -v ../book/images/ ./book/images/
