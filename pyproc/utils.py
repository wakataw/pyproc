import csv
import json
import os
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse

TOKEN_FORMAT = re.compile(r"d\.authenticityToken[\s+]=[\s+]['\"]([0-9a-zA-Z]+)['\"];", re.DOTALL)

GIST_HOST_URL = 'https://gist.githubusercontent.com/wakataw/54d206da0e6238253d364b04bb149cdd/raw'


def parse_token(page):
    token = TOKEN_FORMAT.findall(page)

    if token:
        return token[0]

    return


def get_all_host():
    resp = requests.get('https://satudata.inaproc.id/service/daftarLPSE', timeout=10)
    data = json.loads(resp.content)

    return data


def download_host(logging, name='daftarlpse.csv'):
    data = get_all_host()
    hosts = dict()
    invalid_host = 0

    for item in data:
        try:
            url = item['repo_url4']
        except KeyError:
            url = item['repo_url']

        parsed_url = urlparse(url)

        if not parsed_url.scheme.startswith('http'):
            invalid_host += 1
            continue

        hosts[url] = str(item['repo_id']) + '-' + \
            ' '.join([i for i in re.sub(r'[^a-zA-Z\d\s]', ' ', item['repo_nama']).split() if i.strip() != ''])

    logging.info(
        "{} alamat LPSE ditemukan. {} alamat valid, {} alamat tidak valid, {} alamat terduplikasi.".format(
            len(data), len(hosts), invalid_host, len(data) - len(hosts) - invalid_host
        )
    )
    logging.debug(hosts)

    with open(name, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f, delimiter=';')
        for k, v in hosts.items():
            writer.writerow([k, v])

    logging.info("Export daftar lpse ke {}".format(name))


def download_host_json(logging, name='host.json', directory='.'):
    """
    Download host.json dari GitHub Gist
    :param logging: logging module
    :param name: nama file output
    :param directory: direktori output
    :return: data host dalam format list
    """
    resp = requests.get(GIST_HOST_URL, timeout=30)
    resp.raise_for_status()

    data = resp.json()

    filepath = os.path.join(directory, name)

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    logging.info("Export host.json ke {}".format(filepath))

    return data


def parse_version(version):
    version = tuple(map(int, re.findall(r'(?P<major>\d+).(?P<minor>\d+)u(?P<patch>\d{8})', version)[0]))
    return version
