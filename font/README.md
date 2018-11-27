Subiquity comes with its own console font, which differs from the
standard one in how arrow-like glyphs are rendered; the standard font
renders them as arrowheaded forms like → but we want solid triangles
like ▶.

We also want a check mark (✓) and I don't like the one in h16.bdf.

Make the font using the `make-font.sh` script (can't do it at snap
build time because it uses "apt source").
