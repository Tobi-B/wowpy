from setuptools import setup

setup(
    name='wowpy',
    version='0.1.0',
    author='Tobias Bruns',
    author_email="tbbruns@gmx.de",
    packages=['wowpy', 'wowpy.test'],
    license='LICENCE',
    description='Python package for simple robot control with blockpy etc.',
    long_description=open('README.md').read(),
    install_requires=[
        "bleak",
        "pytest",
        "numpy"
    ]
)

