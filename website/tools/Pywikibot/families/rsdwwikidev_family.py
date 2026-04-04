from pywikibot import family


class Family(family.Family):
    name = "rsdwwikidev"
    langs = {"en": "en_rsdwwiki.dev.weirdgloop.org"}

    def scriptpath(self, code: str) -> str:
        return ""

    def verify_SSL_certificate(self, code: str) -> bool:
        # The dev host uses an underscore in the hostname; disable strict cert
        # hostname validation for this custom family.
        return False
