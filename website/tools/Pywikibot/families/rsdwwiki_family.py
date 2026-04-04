from pywikibot import family


class Family(family.Family):
    name = "rsdwwiki"
    langs = {"en": "dragonwilds.runescape.wiki"}

    def scriptpath(self, code: str) -> str:
        # Dragonwilds wiki API is at /api.php (not /w/api.php).
        return ""
