from enum import Enum


class Language(Enum):
    Unknown = "unk"
    English = "eng"
    French = "fra"
    Portuguese = "por"
    Russian = "rus"
    Spanish = "spa"
    German = "deu"
    Italian = "ita"
    Chinese = "zho"
    Japanese = "jpn"
    Korean = "kor"


class LanguageMap(Enum):
    enus = "eng"
    esmx = "spa"
    frfr = "fra"
    dede = "deu"
    zhtw = "zho"
    jajp = "jpn"
    ruru = "rus"
    ptbr = "por"
    itit = "ita"
    kokr = "kor"

    @classmethod
    def get_value(cls, name_str: str, default: str | None = None) -> str | None:
        try:
            return cls[name_str].value
        except KeyError:
            return default

    @classmethod
    def get_key(cls, value_str: str, default: str | None = None) -> str | None:
        for name, member in cls.__members__.items():
            if member.value == value_str:
                return name
        return default
