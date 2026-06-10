import csv
import json
import logging
import os
import re
import requests

logger = logging.getLogger(__name__)

TOKEN_FORMAT = re.compile(r"d\.authenticityToken[\s+]=[\s+]['\"]([0-9a-zA-Z]+)['\"];", re.DOTALL)

GIST_HOST_URL = 'https://gist.githubusercontent.com/wakataw/54d206da0e6238253d364b04bb149cdd/raw'


def parse_token(page: str):
    token = TOKEN_FORMAT.findall(page)

    if token:
        return token[0]

    return


def get_host_metadata():
    """Return LPSE host metadata from the maintained Gist source."""
    resp = requests.get(GIST_HOST_URL, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return [
        {
            "name": item.get("name"),
            "newUrlPath": item.get("newUrlPath"),
        }
        for item in data
        if isinstance(item, dict)
    ]


def download_host(name: str = 'daftarlpse.csv'):
    """Download host list from Gist metadata and export canonical SPSE URLs to CSV."""
    data = get_host_metadata()
    hosts = dict()
    invalid_host = 0

    for item in data:
        new_url_path = item.get('newUrlPath')
        name_value = item.get('name')
        if not new_url_path or not name_value:
            invalid_host += 1
            continue

        host = re.sub(r'[^a-zA-Z\d\-_]', '', str(new_url_path).strip().lower())
        if not host:
            invalid_host += 1
            continue

        url = f'https://spse.inaproc.id/{host}'
        hosts[url] = ' '.join(str(name_value).split())

    logger.info(
        "{} alamat LPSE ditemukan. {} alamat valid, {} alamat tidak valid, {} alamat terduplikasi.".format(
            len(data), len(hosts), invalid_host, len(data) - len(hosts) - invalid_host
        )
    )
    logger.debug(hosts)

    with open(name, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f, delimiter=';')
        for k, v in hosts.items():
            writer.writerow([k, v])

    logger.info("Export daftar lpse ke {}".format(name))


def download_host_json(name: str = 'host.json', directory: str = '.'):
    """
    Download host.json dari GitHub Gist
    :param name: nama file output
    :param directory: direktori output
    :return: data host dalam format list
    """
    data = get_host_metadata()

    filepath = os.path.join(directory, name)

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    logger.info("Export host.json ke {}".format(filepath))

    return data


def parse_version(version: str):
    version = tuple(map(int, re.findall(r'(?P<major>\d+).(?P<minor>\d+)u(?P<patch>\d{8})', version)[0]))
    return version
