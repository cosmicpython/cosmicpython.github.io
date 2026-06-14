all: build update-book serve

build:
	./generate-html.py

serve: build
	cd dist && python -m http.server 8899

preview: build
	npx wrangler dev

watch-build:
	ls **/*.md **/*.html **/*.xml *.py | entr ./generate-html.py

update-book:  ## assumes book repo is at ../book
	cd ../book && make html
	./copy-and-fix-book-html.py
	rsync -a -v ../book/images/ ./book/images/
