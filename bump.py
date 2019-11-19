import re


def get_version(file, pattern):
    with open(file, 'r') as f:
        content = f.read()

    version = pattern.findall(content)

    print("File: {}, Old Version: {}".format(file, version[0]))


def update_version(file, pattern, new_version):
    with open(file, 'r') as f:
        content = f.read()

    version = pattern.findall(content)
    content = content.replace(version[0], new_version)

    with open(file, 'w') as f:
        f.write(content)

    print("File: {}, Old Version: {}, New Version: {}".format(file, version[0], new_version))


if __name__ == '__main__':
    pattern = re.compile(r"version[\s+='_\"]+(.*)['\"]")
    file_ = ['pyproc/__init__.py']

    for f in file_:
        get_version(f, pattern)

    print("\nUpdate Version")
    new_version = input("New Version: ")

    for f in file_:
        update_version(f, pattern, new_version)

    # update readme
    update_version('README.md', re.compile(r'version-v(\d+\.\d+\.\d+)-'), new_version)
