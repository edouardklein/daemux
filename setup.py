from setuptools import setup, find_packages
from codecs import open
from os import path

__version__ = '0.0.10'

here = path.abspath(path.dirname(__file__))

# Get the long description from the README file
with open(path.join(here, 'README.rst'), encoding='utf-8') as f:
    long_description = f.read()


install_requires = ['sphinx', 'flake8', 'libtmux']
dependency_links = []

setup(
    name='daemux',
    version=__version__,
    description='Daemux uses tmux to let you start, stop, restart'
    ' and check daemons.',
    long_description=long_description,
    url='https://github.com/edouardklein/daemux',
    download_url='https://github.com/edouardklein/daemux/tarball/' +
    __version__,
    license='AGPL',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: GNU Affero General Public'
        ' License v3 or later (AGPLv3+)',
        'Operating System :: POSIX',
        'Programming Language :: Python :: 3 :: Only',
        'Topic :: System :: Monitoring',
        'Topic :: Utilities'
    ],
    keywords='tmux, daemons, background',
    packages=find_packages(exclude=['docs', 'tests*']),
    include_package_data=True,
    author='Edouard Klein',
    install_requires=install_requires,
    dependency_links=dependency_links,
    author_email='myfirstnamemylastname@mailproviderthatstartswithagfromgoogle'
    '.whyshouldibespammed.letmeinputhateveriwantinthisfieldffs.com'
)
