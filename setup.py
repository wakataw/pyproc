from setuptools import setup, find_packages
from os import path


BASE_DIR = path.abspath(path.dirname(__file__))

with open(path.join(BASE_DIR, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='pyproc',
    version='0.1b2019051001',
    description='Python SPSEv4 wrapper',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://gitlab.com/wakataw/pyproc',
    author='Agung Pratama',
    author_email='agungpratama1001@gmail.com',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content :: CGI Tools/Libraries',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Topic :: Utilities',
        'Natural Language :: English',
        'Natural Language :: Indonesian',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3.5',
        'License :: OSI Approved :: MIT License'
    ],
    python_requires='>=3.5',
    install_requires=[
        'requests',
        'BeautifulSoup4',
        'html5lib'
    ],
    entry_points={
        'console_scripts': ['pyproc=scripts.downloader:main']
    },
    project_urls={
        'Bug Reports': 'https://gitlab.com/wakataw/pyproc/issues',
        'Source': 'https://gitlab.com/wakataw/pyproc'
    },
    keywords='api, spse, lpse, pengadaan, procurement, lkpp, lelang, tender',
    packages=find_packages(exclude=['tests', 'examples']),
    zip_safe=True,
    license='MIT'
)
