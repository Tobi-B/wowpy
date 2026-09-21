from setuptools import setup

setup(
    name='wowpy',
    version='0.1.0',
    author='Tobias Bruns',
    author_email="tbbruns@gmx.de",
    packages=['wowpy', 'wowpy.dashboard', 'wowpy.test'],
    package_data={'wowpy.dashboard': ['static/*']},
    license='LICENSE',
    description='Python package for simple robot control with blockpy etc.',
    long_description=open('README.md').read(),
    install_requires=[
        "bleak",
        "numpy",
        "fastapi",
        "uvicorn[standard]",
    ],
    extras_require={
        "test": ["pytest", "httpx"],
    },
)
