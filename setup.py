from __future__ import absolute_import
from setuptools import setup, find_packages


setup(
    name='webfriend',
    description='An API binding and automation control language for the Chrome Remote Debugging API',
    version='0.0.1',
    author='Gary Hetzel',
    author_email='garyhetzel@gmail.com',
    url='https://github.com/ghetzel/webfriend',
    install_requires=[
        'click',
        'click-log',
        'gevent',
        'textx',
        'websocket-client',
        'ephemeral_port_reserve',
        'redlock',
    ],
    packages=find_packages(exclude=['*.tests']),
    entry_points={
        'console_scripts': [
            'webfriend = webfriend.cli:main',
        ],
    },
    classifiers=[],
)
