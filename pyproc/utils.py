import csv
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse

TOKEN_FORMAT = re.compile(r"d\.authenticityToken[\s+]=[\s+]['\"]([0-9a-zA-Z]+)['\"];", re.DOTALL)


def parse_token(page):
    token = TOKEN_FORMAT.findall(page)

    if token:
        return token[0]

    return


def get_all_host(logging, name='daftarlpse.csv'):
    resp = requests.get('https://inaproc.id/lpse')
    soup = BeautifulSoup(resp.content, 'html5lib')
    script_tag = str(soup.find_all('script')[-1])
    title = re.findall(r"title: '(.*)'", script_tag)
    url = map(lambda x: urlparse(x).netloc, re.findall(r"'(https.*)</a></p>", script_tag))

    logging.info("{} alamat LPSE ditemukan".format(len(title)))

    with open(name, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f, delimiter=';')
        for u, t in zip(url, title):
            writer.writerow([u, t])

    logging.info("Export daftar lpse ke {}".format(name))
