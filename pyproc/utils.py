import csv
import json
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
    resp = requests.get('https://satudata.inaproc.id/service/daftarLPSE')
    data = json.loads(resp.content)

    logging.info("{} alamat LPSE ditemukan".format(len(data)))

    with open(name, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f, delimiter=';')
        for item in data:
            try:
                url = item['repo_url4']
            except KeyError:
                url = item['repo_url']
            writer.writerow([url, f"{item['repo_id']}-{item['repo_nama']}"])

    logging.info("Export daftar lpse ke {}".format(name))
