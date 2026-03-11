from pathlib import Path

from setuptools import find_packages, setup

__version__ = '0.1.0'

here = Path(__file__).resolve().parent

# Get the long description from the README file
long_description = (here / 'README.rst').read_text(encoding='utf-8')


install_requires = ['libtmux']
extras_require = {
    'dev': ['coverage', 'flake8', 'pytest', 'sphinx'],
}

setup(
    name='daemux',
    version=__version__,
    description='Daemux uses tmux to let you start, stop, restart'
    ' and check daemons.',
    long_description=long_description,
    long_description_content_type='text/x-rst',
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
    extras_require=extras_require,
    author_email='myfirstnamemylastname@mailproviderthatstartswithagfromgoogle'
    '.whyshouldibespammed.letmeinputhateveriwantinthisfieldffs.com'
)
