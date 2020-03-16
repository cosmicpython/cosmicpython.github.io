serve:
	python -m http.server --directory=_site 8888

build:
	./generate-html

watch-build:
	ls **/*.md **/*.html *.py | entr ./generate-html.py
