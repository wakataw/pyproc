import re

TOKEN_FORMAT = re.compile(r"d\.authenticityToken[\s+]=[\s+]['\"]([0-9a-zA-Z]+)['\"];", re.DOTALL)


def parse_token(page):
    token = TOKEN_FORMAT.findall(page)

    if token:
        return token[0]

    return


def get_pemenang_from_hasil_evaluasi(hasil):
    keys = hasil[0].keys()
    filter_by_key = lambda key: list(filter(lambda x: x[key], hasil))
    pemenang = None

    if 'pk' in keys:
        pemenang = filter_by_key('pk')

    if not pemenang and 'v' in keys:
        pemenang = filter_by_key('v')

    if not pemenang and 'p' in keys:
        pemenang = filter_by_key('p')

    return pemenang
