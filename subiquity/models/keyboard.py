from lxml import etree


class Keyboard:
    def __init__(self, code, desc):
        self.code = code
        self.desc = desc
        self.variants = {}
        self.languages = set()
    def __repr__(self):
        return "Keyboard({}, {}) {} {}".format(self.code, self.desc, self.variants, self.languages)


class KeyboardModel:
    def __init__(self):
        self.keyboards = [] # Keyboard objects

    def parse(self, fname):
        t = etree.parse(fname)
        for layout in t.xpath("//layoutList/layout"):
            c = layout.find("configItem")
            code = c.find("name").text
            description = c.find("description").text
            keyboard = Keyboard(code, description)
            for lang in c.xpath("languageList/iso639Id/text()"):
                keyboard.languages.add(lang)
            for v in layout.xpath("variantList/variant/configItem"):
                keyboard.variants[v.find("name").text] = v.find("description").text
            self.keyboards.append(keyboard)


def main():
    keyboards = {}


if __name__ == "__main__":
    main()
