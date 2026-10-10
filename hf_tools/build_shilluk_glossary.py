#!/usr/bin/env python3
"""Build aa_config/glossary_shk.csv: a sourced Shilluk word list for the weekly advisory, taken from
Remijsen & Ayoker, Shilluk Lexicography With Audio Data, 2nd ed. (2024), https://doi.org/10.7488/ds/7770
(Lwak and Gar dialects). Usage: python hf_tools/build_shilluk_glossary.py Lexicography_Edition2.docx
Only looks words up; it never composes Shilluk text. Check the dataset's licence before redistributing."""
import csv, os, sys, unicodedata
import docx
N = lambda s: unicodedata.normalize("NFC", s).lower().strip()
# (English, Shilluk orthography, word-class prefix, used for)
W = [
('rain','kødh','noun, singular','rain'),('rainy season','cwir','noun','season'),('dry season','lew','noun','dry spell'),
('drought','mel','noun, singular','drought; dry spell'),('flood (noun, from heavy rain)','mud','noun','flood'),('flood (noun, from a river)','baayø','noun','flood'),
('flood (verb, river)','beedh','intransitive','flood'),('river','nam','noun','river gauges'),('water','pï','noun','water'),('cloud','pøølø','noun, singular','weather'),
('storm','atunø','noun','storm'),('wind','yømø','noun','weather'),('thunder','määrø','noun','weather'),('lightning','ogwel','noun','weather'),
('sun / day','cäng','noun, singular','heat; day'),('hot (adjective)','lyëdh','adjective','heat'),('heat (noun)','lyëdh','noun','heat'),('very cold','lip','adjective','temperature'),
('night','wär','noun, singular','time'),('month','dwäy','noun, singular','time'),('week','osboo','noun, singular','weekly'),('tomorrow','dhuki','adverb','time'),
('soil / earth / mud','läbø','noun','soil'),('earth, ground','piny','noun','higher ground'),('dust','tør','noun','dry spell'),('mud','bub','noun','flood'),
('hill','kwøømø','noun, singular','higher ground'),('island','kaagø','noun, singular','higher ground'),('high river bank','gëlø','noun, singular','higher ground'),
('canal (dug from river)','agal','noun, singular','water'),('well','yith','noun, singular','water points'),('shade','tïbø','noun','heat'),
('fire break / line','ged','noun, singular','fire lines (heat)'),
('field / farm','pwödhø','noun, singular','agriculture'),('hoe','køj','noun','agriculture'),('garden','bag','noun','agriculture'),('grow (a crop, a child)','piidh','transitive','agriculture'),
('maize','ábwög','noun','agriculture'),('white sorghum','bøwi','noun','agriculture'),('rice (plant)','pedh','noun','agriculture'),('rice (kernels)','álaabø','noun','agriculture'),
('seeds / seedlings','köödh','noun','seed'),('harvest (also: bite)','kaaj','transitive','agriculture'),('food','gïncam','noun','food'),('hunger, famine','käj','noun','hunger'),('milk','cag','noun','livestock'),
('cattle','dhök','noun','livestock'),('cattle camp','kaal','noun, singular','livestock'),('goats','dyëg','noun','livestock'),('goat or sheep','dyel','noun, singular','livestock'),
('boat','yäy','noun, singular','boats'),('canoe','cørøg','noun, singular','boats'),('mosquito','bäyø','noun','malaria'),('hospital','ødyadh','noun','health'),('doctor','akïm','noun','health'),
('diarrhoea (also small intestine)','cïn','noun','cholera, disease'),('cough','wøøl','intransitive','health'),('fever / heat (essence noun)','lëdhø','noun','health'),
('person with a disability','bøl','noun, singular','community'),('old person','yuu','noun','community'),('children','nyig','noun','community'),('people','jii','noun','community'),
('chief, leader','jagø','noun, singular','community'),('leader','pëëji','noun','community'),('house','ød','noun','community'),('shelter','akanø','noun, singular','community'),
('message','wöödø','noun','communication'),('word','lögø','noun','communication'),('radio','räädi','noun','communication'),
('boil (a liquid, e.g. water)','waal','transitive','boil water'),('wash (somebody or something)','lwøøg','transitive','hand washing'),('drink','maadh','transitive','drinking water'),
('eat','thøl','transitive','food'),('build','geer','transitive','dykes, fire lines'),('gather','gween','transitive','community'),('share','nywaag','transitive','share high ground'),
('hide / keep safe','kaan','transitive','store seed'),('call','cwøøl','transitive','communication'),('tell','kwøøb','transitive','warn'),('speak','kööb','intransitive','communication'),
('escape death, survive','bødh','intransitive','flood'),('move','caag','transitive','move animals'),('fear','bwøøg','transitive','danger'),('come','bï','intransitive','general'),
('stop','joog','transitive','general'),('give','muuj','intransitive','general'),('see','liidh','transitive','watch the river'),('dry up (also: stop giving milk)','dwöön','intransitive','dry spell'),
('fall','päädh','intransitive','general'),('all','bënn','quantifier','general'),('few','nøg','quantifier','general'),('bad','raj','adjective','general'),('far','läwi','adjective','general'),('near','buti','noun','general'),
]
KW = {'flood (noun, from heavy rain)': 'flooding', 'night': 'night', 'hoe': 'hoe', 'move': 'move', 'wash (somebody or something)': 'wash'}


def main(path, out):
    t = max(docx.Document(path).tables, key=lambda t: len(t.rows))
    rows = [[c.text.strip() for c in r.cells] for r in t.rows][1:]
    res, miss = [], []
    for en, orth, cls, use in W:
        h = [r for r in rows if N(r[1]) == N(orth) and r[2].startswith(cls.split(",")[0])]
        exact = [r for r in h if r[2].startswith(cls)]
        h = exact or h
        if en in KW:
            h = [r for r in h if KW[en] in r[4].lower().split(';')[0]] or h
        if not h:
            miss.append((en, orth)); continue
        r = h[0]
        res.append(dict(english=en, shilluk=r[1], entry_form=r[0], word_class=r[2], lexicon_meaning=r[4].split(";")[0][:140],
                        forms_or_examples=r[3][:80], used_for=use, other_matches=len(h) - 1,
                        source="Remijsen & Ayoker 2024, 2nd ed., doi:10.7488/ds/7770"))
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(res[0])); w.writeheader(); w.writerows(res)
    print(f"{len(res)} words written to {out}; not found: {miss}")
if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "aa_config", "glossary_shk.csv"))
