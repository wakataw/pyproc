import csv
import re
import requests
from bs4 import BeautifulSoup

TOKEN_FORMAT = re.compile(r"d\.authenticityToken[\s+]=[\s+]['\"]([0-9a-zA-Z]+)['\"];", re.DOTALL)


def parse_token(page):
    token = TOKEN_FORMAT.findall(page)

    if token:
        return token[0]

    return


def get_all_host(name='daftarlpse.csv'):
    resp = requests.get('https://inaproc.id/lpse')
    soup = BeautifulSoup(resp.content, 'html5lib')
    title = []
    url = []

    for line in soup.find_all('script')[2].text.split('\n'):
        line = line.strip()

        if line.startswith('title: '):
            title.append(
                line.strip().replace('title: ', '').replace('\'', '')
            )

        if line.startswith('\'http'):
            url.append(line.split('<')[0].strip()[1:])

    print("{} alamat LPSE ditemukan".format(len(url)))

    with open(name, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f, delimiter=';')
        for u, t in zip(url, title):
            writer.writerow([u, t])

    print("Export daftar lpse ke {}".format(name))
