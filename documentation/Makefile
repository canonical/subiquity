SRC = $(wildcard *.md)
HTML = $(addprefix html/, $(SRC:.md=.html))

html/%.html: %.md
	@mkdir --parents html
	markdown $^ > $@
	pandoc $^ --standalone --output $@

.PHONY: all
all: $(HTML)

.PHONY: clean
clean:
	$(RM) $(HTML)
	$(RM) -d html
