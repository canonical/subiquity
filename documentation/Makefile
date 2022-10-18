SRC = $(wildcard *.md)

DISCOURSE_MD = $(addprefix discourse/, $(SRC))
HTML_MD = $(addprefix html/, $(SRC))
HTML = $(HTML_MD:.md=.html)

discourse/%.md: %.md
	@mkdir --parents discourse
	python3 ./substitute-links.py md-to-discourse --input $^ --output $@

html/%.md: %.md
	@mkdir --parents html
	python3 ./substitute-links.py md-to-html --input $^ --output $@

%.html: %.md
	pandoc $^ --standalone --output $@

.PHONY: html
html: $(HTML)

.PHONY: discourse
discourse: $(DISCOURSE_MD)

.PHONY: clean
clean:
	$(RM) $(DISCOURSE_MD)
	$(RM) -d discourse
	$(RM) $(HTML)
	$(RM) -d html
