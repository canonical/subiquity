Subiquity comes with its own console font, which differs from the
standard one in how arrow-like glyphs are rendered; the standard font
renders them as arrowheaded forms like → but we want solid triangles
like ▶.

I built the font like this:


```
$ apt source console-setup
$ cd console-setup-*/Fonts
$ cat > my.equivalents <<EOF
U+2191 U+25B4 U+25B2
# U+2191:   UPWARDS ARROW
# U+25B4:   BLACK UP-POINTING SMALL TRIANGLE
# U+25B2:   BLACK UP-POINTING TRIANGLE
U+2193 U+25BE U+25BC
# U+2193:   DOWNWARDS ARROW
# U+25BE:   BLACK DOWN-POINTING SMALL TRIANGLE
# U+25BC:   BLACK DOWN-POINTING TRIANGLE
U+2190 U+25C2 U+25C0
# U+2190:   LEFTWARDS ARROW
# U+25C2:   BLACK LEFT-POINTING SMALL TRIANGLE
# U+25C0:   BLACK LEFT-POINTING TRIANGLE
U+2192 U+25B8 U+25B6
# U+2192:   RIGHTWARDS ARROW
# U+25B8:   BLACK RIGHT-POINTING SMALL TRIANGLE
# U+25B6:   BLACK RIGHT-POINTING TRIANGLE
EOF
$ ./bdf2psf --log ./my.log  ./bdf/georgian16.bdf+./bdf/unifont.bdf+./bdf/h16.bdf+./bdf/etl16-unicode.bdf  ./standard.equivalents+./my.equivalents  ./ascii.set+./linux.set+./fontsets/Uni2.512+:./useful.set 512 ./subiquity.psf
```
